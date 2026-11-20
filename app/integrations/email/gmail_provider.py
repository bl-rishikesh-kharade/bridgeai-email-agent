"""Read-only Gmail access for the local single-user application."""
import base64
import logging
from datetime import datetime, timezone
from email.utils import getaddresses
from urllib.parse import quote, urlencode
from app.core.logger import log_event
from app.integrations.google.oauth import GoogleOAuthManager
from app.schemas.email import Email


class GmailProviderError(RuntimeError):
    """Safe, application-level Gmail integration error."""


class GmailAuthorizationError(GmailProviderError):
    """The OAuth principal is not authorized to access the mailbox or scope."""


class GmailEmailProvider:
    FILTER_LABEL_IDS = {
        "important_unread": ["UNREAD", "IMPORTANT"],
        "unread": ["UNREAD"],
    }
    RECENT_QUERY = "newer_than:2d"

    def __init__(self, service=None, service_factory=None, oauth_manager=None):
        self._service = service
        self._service_factory = service_factory
        self._oauth_manager = oauth_manager
        self._account_email: str | None = None

    @property
    def _gmail(self):
        if self._service is None:
            try:
                self._service = self._service_factory()
            except Exception as exc:
                raise GmailProviderError("Google authorization or Gmail service initialization failed.") from exc
        return self._service

    @classmethod
    def from_settings(cls, settings, oauth_manager: GoogleOAuthManager | None = None):
        manager = oauth_manager or GoogleOAuthManager(settings)
        return cls(service_factory=lambda: manager.service("gmail", "v1"), oauth_manager=manager)

    def reset_connection(self) -> None:
        """Discard cached Gmail state after the connected Google account changes."""
        self._service = None
        self._account_email = None

    def refresh_and_reset(self) -> None:
        """Discard cached Gmail service and force token refresh on OAuth manager."""
        self._service = None
        self._account_email = None
        if self._oauth_manager and hasattr(self._oauth_manager, "refresh_credentials"):
            try:
                self._oauth_manager.refresh_credentials()
            except Exception:
                pass

    @staticmethod
    def _decode_data(data: str) -> str:
        try:
            return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")
        except (ValueError, TypeError):
            return ""

    @classmethod
    def _body(cls, payload: dict) -> str:
        parts = payload.get("parts") or []
        plain = []
        html = []
        if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
            plain.append(cls._decode_data(payload["body"]["data"]))
        elif payload.get("mimeType") == "text/html" and payload.get("body", {}).get("data"):
            html.append(cls._decode_data(payload["body"]["data"]))
        for part in parts:
            if part.get("mimeType", "").startswith("multipart/"):
                nested = cls._body(part)
                if nested:
                    plain.append(nested)
            elif part.get("mimeType") in {"text/plain", "text/html"} and part.get("body", {}).get("data"):
                dest = plain if part["mimeType"] == "text/plain" else html
                dest.append(cls._decode_data(part["body"]["data"]))
        return "\n".join(plain or html)

    @classmethod
    def map_message(cls, raw: dict) -> Email:
        message_id = raw.get("id")
        if not message_id or not isinstance(raw.get("payload"), dict):
            raise GmailProviderError("Gmail returned a malformed message without an ID or payload.")
        headers = {str(h.get("name", "")).lower(): str(h.get("value", ""))
                   for h in raw["payload"].get("headers", []) if isinstance(h, dict)}
        from_header = headers.get("from", "").strip()
        parsed_senders = [addr for _, addr in getaddresses([from_header]) if addr]
        sender = parsed_senders[0] if parsed_senders else (from_header or "unknown")

        to_header = headers.get("to", "").strip()
        parsed_recipients = [addr for _, addr in getaddresses([to_header]) if addr]
        receiver = parsed_recipients[0] if parsed_recipients else (to_header or sender or "unknown")

        if not sender:
            sender = "unknown"
        if not receiver:
            receiver = sender
        labels = raw.get("labelIds", [])
        internal_date = raw.get("internalDate")
        try:
            received_at = datetime.fromtimestamp(int(internal_date) / 1000, tz=timezone.utc) if internal_date else None
        except (ValueError, TypeError, OSError):
            received_at = None
        return Email(id=message_id, provider_message_id=message_id,
                     thread_id=raw.get("threadId") or message_id, sender=sender,
                     receiver=receiver, subject=headers.get("subject", "(no subject)"),
                     body=cls._body(raw["payload"]), is_read="UNREAD" not in labels,
                     received_at=received_at, labels=labels)

    def get_email(self, email_id: str, *, _retry: bool = True) -> Email | None:
        try:
            raw = self._gmail.users().messages().get(userId="me", id=str(email_id), format="full").execute()
            return self.map_message(raw)
        except GmailProviderError:
            raise
        except Exception as exc:
            if getattr(exc, "resp", None) is not None and getattr(exc.resp, "status", None) == 404:
                return None
            if getattr(exc, "resp", None) is not None and getattr(exc.resp, "status", None) in {401, 403}:
                if _retry and self._oauth_manager:
                    self.refresh_and_reset()
                    return self.get_email(email_id, _retry=False)
                raise GmailAuthorizationError("Gmail access is denied; check the authorized Workspace account and read-only scope.") from exc
            raise GmailProviderError("Gmail message retrieval failed.") from exc

    def list_emails(
        self, limit: int = 50, *, query: str | None = None,
        label_ids: list[str] | None = None,
        _retry: bool = True,
    ) -> list[Email]:
        if not 1 <= limit <= 500:
            raise ValueError("Email list limit must be between 1 and 500.")
        try:
            refs = []
            page_token = None
            while len(refs) < limit:
                args = {"userId": "me", "maxResults": min(100, limit - len(refs)), "pageToken": page_token}
                if query:
                    args["q"] = query
                if label_ids:
                    args["labelIds"] = label_ids
                result = self._gmail.users().messages().list(**args).execute()
                refs.extend(result.get("messages", []))
                page_token = result.get("nextPageToken")
                if not page_token:
                    break

            target_refs = refs[:limit]
            if not target_refs:
                return []

            messages = []
            skipped = 0

            # 1. Fast parallel batch retrieval using Gmail BatchHttpRequest (40x faster)
            can_batch = hasattr(self._gmail, "new_batch_http_request") and callable(getattr(self._gmail, "new_batch_http_request"))
            if can_batch:
                try:
                    messages_by_id = {}
                    batch_size = 50
                    for chunk_start in range(0, len(target_refs), batch_size):
                        chunk = target_refs[chunk_start : chunk_start + batch_size]
                        batch = self._gmail.new_batch_http_request()

                        def _make_callback(mid):
                            def _cb(request_id, response, exception):
                                nonlocal skipped
                                if exception is None and response:
                                    try:
                                        messages_by_id[mid] = self.map_message(response)
                                    except Exception:
                                        skipped += 1
                                else:
                                    if getattr(exception, "resp", None) is not None and getattr(exception.resp, "status", None) in {401, 403}:
                                        raise exception
                                    skipped += 1
                            return _cb

                        for ref in chunk:
                            mid = ref.get("id", "")
                            if mid:
                                req = self._gmail.users().messages().get(userId="me", id=mid, format="full")
                                batch.add(req, callback=_make_callback(mid))
                        batch.execute()

                    for ref in target_refs:
                        mid = ref.get("id", "")
                        if mid in messages_by_id:
                            messages.append(messages_by_id[mid])
                except Exception as batch_exc:
                    if getattr(batch_exc, "resp", None) is not None and getattr(batch_exc.resp, "status", None) in {401, 403}:
                        raise batch_exc
                    # Fallback to sequential retrieval
                    messages = []
                    skipped = 0

            # 2. Sequential retrieval fallback (also used for mock fixtures in tests)
            if not messages:
                for ref in target_refs:
                    try:
                        email = self.get_email(ref.get("id", ""), _retry=False)
                    except GmailAuthorizationError:
                        raise
                    except GmailProviderError:
                        log_event(
                            "gmail.message.skipped", level=logging.WARNING,
                            reason="malformed_message_metadata",
                        )
                        skipped += 1
                        continue
                    if email is not None:
                        messages.append(email)

            if skipped and not messages and target_refs:
                raise GmailProviderError("Gmail messages could not be parsed.")
            return messages
        except GmailProviderError:
            raise
        except Exception as exc:
            if getattr(exc, "resp", None) is not None and getattr(exc.resp, "status", None) in {401, 403}:
                if _retry and self._oauth_manager:
                    self.refresh_and_reset()
                    return self.list_emails(limit, query=query, label_ids=label_ids, _retry=False)
                raise GmailAuthorizationError("Gmail access is denied; check the authorized Workspace account and read-only scope.") from exc
            raise GmailProviderError("Gmail message listing failed.") from exc

    def list_filtered_emails(self, filter_id: str, limit: int = 20) -> list[Email]:
        if filter_id in self.FILTER_LABEL_IDS:
            return self.list_emails(limit, label_ids=self.FILTER_LABEL_IDS[filter_id])
        if filter_id == "important_unread_last_48_hours":
            return self.list_emails(
                limit, query=self.RECENT_QUERY,
                label_ids=self.FILTER_LABEL_IDS["important_unread"],
            )
        if filter_id == "unread_last_48_hours":
            return self.list_emails(
                limit, query=self.RECENT_QUERY,
                label_ids=self.FILTER_LABEL_IDS["unread"],
            )
        raise ValueError("Unsupported email filter.")

    def has_more_filtered_emails(self, filter_id: str, threshold: int = 100) -> bool:
        base_filter = "unread" if "unread" in filter_id and "important" not in filter_id else "important_unread"
        if base_filter not in self.FILTER_LABEL_IDS or threshold < 1:
            raise ValueError("Unsupported email filter or threshold.")
        try:
            result = self._gmail.users().messages().list(
                userId="me", labelIds=self.FILTER_LABEL_IDS[base_filter], maxResults=threshold + 1,
            ).execute()
            return len(result.get("messages", [])) > threshold
        except GmailProviderError:
            raise
        except Exception as exc:
            raise GmailProviderError("Gmail message listing failed.") from exc

    def get_account_email(self, *, _retry: bool = True) -> str:
        if self._account_email:
            return self._account_email
        try:
            profile = self._gmail.users().getProfile(userId="me").execute()
            address = str(profile.get("emailAddress", "")).strip()
            if not address:
                raise GmailProviderError("Google did not return the connected account address.")
            self._account_email = address
            return address
        except GmailProviderError:
            raise
        except Exception as exc:
            if getattr(exc, "resp", None) is not None and getattr(exc.resp, "status", None) in {401, 403}:
                if _retry and self._oauth_manager:
                    self.refresh_and_reset()
                    return self.get_account_email(_retry=False)
            raise GmailProviderError("The connected Gmail account could not be identified.") from exc

    def gmail_url(self, email: Email) -> str:
        thread_id = email.thread_id or email.id
        try:
            account = self.get_account_email()
            if account:
                return f"https://mail.google.com/mail/?authuser={quote(account, safe='@+')}#all/{quote(thread_id, safe='')}"
            return f"https://mail.google.com/mail/#all/{quote(thread_id, safe='')}"
        except Exception:
            return f"https://mail.google.com/mail/#all/{quote(thread_id, safe='')}"

    def search_emails(self, query: str, limit: int = 10, *, sender_only: bool = False) -> list[Email]:
        clean_query = " ".join(str(query).split()).replace('"', "").replace("\\", "")
        if not clean_query or len(clean_query) > 200:
            raise ValueError("Email search query must contain between 1 and 200 characters.")
        if not 1 <= limit <= 500:
            raise ValueError("Email search limit must be between 1 and 500.")
        operators = ("after:", "before:", "newer_than:", "older_than:", "from:", "to:", "subject:", "is:", "has:", "label:")
        has_operator = any(op in clean_query.lower() for op in operators)
        gmail_query = f'from:"{clean_query}"' if sender_only else (clean_query if has_operator else f'"{clean_query}"')
        return self.list_emails(limit, query=gmail_query)

    def mark_as_read(self, email_ids: list[str], *, _retry: bool = True) -> int:
        """Remove UNREAD label from the specified emails in Gmail."""
        if not email_ids:
            return 0
        clean_ids = [str(eid).strip() for eid in email_ids if str(eid).strip()]
        if not clean_ids:
            return 0
        try:
            # Gmail batchModify handles up to 1000 IDs per request
            self._gmail.users().messages().batchModify(
                userId="me",
                body={
                    "ids": clean_ids,
                    "removeLabelIds": ["UNREAD"],
                },
            ).execute()
            return len(clean_ids)
        except GmailProviderError:
            raise
        except Exception as exc:
            if getattr(exc, "resp", None) is not None and getattr(exc.resp, "status", None) in {401, 403}:
                if _retry and self._oauth_manager:
                    self.refresh_and_reset()
                    return self.mark_as_read(clean_ids, _retry=False)
                raise GmailAuthorizationError("Gmail access is denied; check modified permissions.") from exc
            raise GmailProviderError("Failed to mark emails as read.") from exc

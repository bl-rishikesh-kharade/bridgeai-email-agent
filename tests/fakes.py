"""In-memory fakes used only by automated tests."""

from app.schemas.email import Email


class FakeEmailProvider:
    def __init__(self, emails: list[Email] | None = None):
        self._emails = {email.id: email for email in (emails or [])}

    def get_email(self, email_id: str) -> Email | None:
        return self._emails.get(str(email_id))

    def list_emails(self, limit: int = 50) -> list[Email]:
        return list(self._emails.values())[:limit]

    def search_emails(self, query: str, limit: int = 10, *, sender_only: bool = False) -> list[Email]:
        terms = [term.casefold() for term in query.split() if term]
        if not terms or not 1 <= limit <= 500:
            raise ValueError("Invalid fake email search query or limit.")
        matches = []
        for email in self._emails.values():
            searchable = str(email.sender) if sender_only else " ".join(
                (str(email.sender), str(email.receiver), email.subject, email.body)
            )
            if all(term in searchable.casefold() for term in terms):
                matches.append(email)
        return matches[:limit]

    def list_filtered_emails(self, filter_id: str, limit: int = 20) -> list[Email]:
        if filter_id in {"important_unread", "important_unread_last_48_hours"}:
            matches = [email for email in self._emails.values()
                       if not email.is_read and any(label.casefold() == "important" for label in email.labels)]
        elif filter_id in {"unread", "unread_last_48_hours"}:
            matches = [email for email in self._emails.values() if not email.is_read]
        else:
            raise ValueError("Unsupported fake email filter.")
        return matches[:limit]

    def has_more_filtered_emails(self, filter_id: str, threshold: int = 100) -> bool:
        if "important" in filter_id:
            matches = [email for email in self._emails.values()
                       if not email.is_read and any(label.casefold() == "important" for label in email.labels)]
        else:
            matches = [email for email in self._emails.values() if not email.is_read]
        return len(matches) > threshold

    def get_account_email(self) -> str:
        return "user@example.com"

    def gmail_url(self, email: Email) -> str:
        return f"https://mail.google.com/mail/#all/{email.id}"

    def reset_connection(self) -> None:
        pass

import json
from fastapi import APIRouter, Request

from app.schemas.agent import AgentChatRequest, AgentChatResponse, MarkEmailsReadRequest, MarkEmailsReadResponse
from app.integrations.email.gmail_provider import GmailEmailProvider
from app.services.email_summary import batch_summarize_emails, extract_clean_summary


def build_router(chat_service, email_provider, oauth_manager=None):
    router = APIRouter(prefix="/agent", tags=["agent"])

    def _resolve_request_provider(http_request: Request):
        if oauth_manager:
            auth_cookie = http_request.cookies.get("bridgeai_session_token")
            if auth_cookie:
                try:
                    import base64
                    if auth_cookie.startswith("{"):
                        token_data = json.loads(auth_cookie)
                    else:
                        pad = 4 - (len(auth_cookie) % 4)
                        if pad != 4:
                            auth_cookie += "=" * pad
                        token_data = json.loads(base64.urlsafe_b64decode(auth_cookie.encode("ascii")).decode("utf-8"))
                    creds = oauth_manager.credentials_from_token(token_data)
                    return GmailEmailProvider(service_factory=lambda: oauth_manager.service("gmail", "v1", creds=creds), oauth_manager=oauth_manager)
                except Exception:
                    pass
        return email_provider

    @router.post("/chat", response_model=AgentChatResponse)
    def chat(request: AgentChatRequest, http_request: Request):
        try:
            active_provider = _resolve_request_provider(http_request)
            result = chat_service.handle_request({
                "message": request.message,
                "filter_id": request.filter_id,
                "selected_email_id": request.selected_email_id,
                "history": [turn.model_dump() for turn in request.history],
                "email_provider": active_provider,
            })
            email_results = result.get("email_results", [])
            reviews_by_email_id = {
                review["email_id"]: review
                for review in result.get("email_reviews", [])
                if review.get("email_id")
            }
            # Run fast, pure local 4-stage summarization across all emails (0 API calls/tokens)
            unreviewed = [e for e in email_results if not reviews_by_email_id.get(e.id, {}).get("summary")]
            batch_summaries = batch_summarize_emails(unreviewed) if unreviewed else {}

            return AgentChatResponse(
                response=result.get("response", "I couldn't complete that request."),
                current_email_id=result.get("current_email_id"),
                used_recent_window=result.get("used_recent_window", False),
                auth_required=result.get("auth_required", False),
                email_options=[
                    {
                        "id": email.id,
                        "gmail_url": active_provider.gmail_url(email),
                        "subject": email.subject,
                        "sender": str(email.sender),
                        "receiver": str(email.receiver),
                        "body_snippet": email.body[:300].strip() if email.body else None,
                        "received_at": email.received_at,
                        "summary": (
                            reviews_by_email_id.get(email.id, {}).get("summary")
                            or batch_summaries.get(email.id)
                            or extract_clean_summary(email.body)
                        ),
                        "priority": reviews_by_email_id.get(email.id, {}).get("priority"),
                        "requires_action": reviews_by_email_id.get(email.id, {}).get("requires_action"),
                        "requires_attention": reviews_by_email_id.get(email.id, {}).get("requires_attention"),
                        "action_items": reviews_by_email_id.get(email.id, {}).get("action_items", []),
                    }
                    for email in email_results
                ],
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("Unexpected error in /agent/chat: %s", exc)
            return AgentChatResponse(
                response="I couldn't complete that request right now. Please try again.",
                auth_required=False,
                email_options=[],
            )

    @router.post("/emails/mark-read", response_model=MarkEmailsReadResponse)
    def mark_emails_read(request: MarkEmailsReadRequest, http_request: Request):
        active_provider = _resolve_request_provider(http_request)
        try:
            count = active_provider.mark_as_read(request.email_ids)
            return MarkEmailsReadResponse(success=True, marked_count=count, marked_ids=request.email_ids)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("Failed to mark emails as read: %s", exc)
            return MarkEmailsReadResponse(success=False, marked_count=0, marked_ids=[])

    return router

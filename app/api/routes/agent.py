import logging
from fastapi import APIRouter, Request, Response

from app.core.session import resolve_session_provider
from app.schemas.agent import AgentChatRequest, AgentChatResponse, MarkEmailsReadRequest, MarkEmailsReadResponse
from app.services.email_summary import batch_summarize_emails, extract_clean_summary, extract_meeting_url

logger = logging.getLogger(__name__)


def build_router(chat_service, email_provider, oauth_manager=None):
    router = APIRouter(prefix="/agent", tags=["agent"])

    @router.post("/chat", response_model=AgentChatResponse)
    def chat(request: AgentChatRequest, http_request: Request, http_response: Response):
        try:
            active_provider, _ = resolve_session_provider(
                request=http_request,
                response=http_response,
                oauth_manager=oauth_manager,
                fallback_provider=email_provider,
            )
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
                        "meeting_url": extract_meeting_url(email.body),
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
    def mark_emails_read(request: MarkEmailsReadRequest, http_request: Request, http_response: Response):
        active_provider, _ = resolve_session_provider(
            request=http_request,
            response=http_response,
            oauth_manager=oauth_manager,
            fallback_provider=email_provider,
        )
        try:
            count = active_provider.mark_as_read(request.email_ids)
            return MarkEmailsReadResponse(success=True, marked_count=count, marked_ids=request.email_ids)
        except Exception as exc:
            logger.exception("Failed to mark emails as read: %s", exc)
            return MarkEmailsReadResponse(success=False, marked_count=0, marked_ids=[])

    return router

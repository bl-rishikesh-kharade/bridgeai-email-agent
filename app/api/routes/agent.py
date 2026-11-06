import json
from fastapi import APIRouter, Request

from app.schemas.agent import AgentChatRequest, AgentChatResponse
from app.integrations.email.gmail_provider import GmailEmailProvider


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
                    return GmailEmailProvider(service_factory=lambda: oauth_manager.service("gmail", "v1", creds=creds))
                except Exception:
                    pass
        return email_provider

    @router.post("/chat", response_model=AgentChatResponse)
    def chat(request: AgentChatRequest, http_request: Request):
        active_provider = _resolve_request_provider(http_request)
        result = chat_service.handle_request({
            "message": request.message,
            "filter_id": request.filter_id,
            "selected_email_id": request.selected_email_id,
            "history": [turn.model_dump() for turn in request.history],
            "email_provider": active_provider,
        })
        reviews_by_email_id = {
            review["email_id"]: review
            for review in result.get("email_reviews", [])
            if review.get("email_id")
        }
        return AgentChatResponse(
            response=result.get("response", "I couldn't complete that request."),
            current_email_id=result.get("current_email_id"),
            used_recent_window=result.get("used_recent_window", False),
            email_options=[
                {
                    "id": email.id,
                    "gmail_url": active_provider.gmail_url(email),
                    "subject": email.subject,
                    "sender": str(email.sender),
                    "receiver": str(email.receiver),
                    "body_snippet": email.body[:300].strip() if email.body else None,
                    "received_at": email.received_at,
                    "summary": reviews_by_email_id.get(email.id, {}).get("summary"),
                    "priority": reviews_by_email_id.get(email.id, {}).get("priority"),
                    "requires_action": reviews_by_email_id.get(email.id, {}).get("requires_action"),
                    "requires_attention": reviews_by_email_id.get(email.id, {}).get("requires_attention"),
                    "action_items": reviews_by_email_id.get(email.id, {}).get("action_items", []),
                }
                for email in result.get("email_results", [])
            ],
        )

    return router

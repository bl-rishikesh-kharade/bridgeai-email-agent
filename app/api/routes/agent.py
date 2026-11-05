from fastapi import APIRouter

from app.schemas.agent import AgentChatRequest, AgentChatResponse


def build_router(chat_service, email_provider):
    router = APIRouter(prefix="/agent", tags=["agent"])

    @router.post("/chat", response_model=AgentChatResponse)
    def chat(request: AgentChatRequest):
        result = chat_service.handle_request({
            "message": request.message,
            "filter_id": request.filter_id,
            "selected_email_id": request.selected_email_id,
            "history": [turn.model_dump() for turn in request.history],
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
                    "gmail_url": email_provider.gmail_url(email),
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

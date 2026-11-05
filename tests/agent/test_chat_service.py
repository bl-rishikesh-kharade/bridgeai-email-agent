from app.schemas.email import Email
from app.services.chat_service import build_chat_service
from app.services.ai_service import AgentToolCall, AgentTurn
from tests.fakes import FakeEmailProvider


def test_chat_service_can_be_constructed_with_providers():
    service = build_chat_service(FakeEmailProvider())
    assert service is not None


def test_chat_service_graceful_fallback_when_gemini_fails_after_tool_call():
    sample_email = Email(
        id="msg-1",
        provider_message_id="msg-1",
        sender="sender@example.com",
        receiver="user@example.com",
        subject="Test Subject",
        body="Test Body",
        is_read=False,
        labels=[],
    )
    provider = FakeEmailProvider([sample_email])
    call_count = 0

    def mock_model_turn(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Turn 1: tool call to list emails
            return AgentTurn(
                text="",
                tool_calls=[AgentToolCall(name="list_recent_emails", arguments={"limit": 2})],
                model_content=None,
            )
        # Turn 2: Gemini fails with 503
        raise RuntimeError("503 UNAVAILABLE: Model experiencing high demand")

    service = build_chat_service(provider, model_turn=mock_model_turn)
    result = service.handle_request({"message": "list my emails", "history": []})

    # Even though Gemini failed on Turn 2, the user gets a helpful response and the emails are preserved!
    assert "found in your mailbox" in result["response"]
    assert len(result["email_results"]) == 1


def test_chat_service_quota_error_message():
    provider = FakeEmailProvider()

    def mock_model_turn(*args, **kwargs):
        exc = RuntimeError("429 RESOURCE_EXHAUSTED: Rate limit exceeded")
        setattr(exc, "code", 429)
        raise exc

    service = build_chat_service(provider, model_turn=mock_model_turn)
    result = service.handle_request({"message": "hey", "history": []})

    assert "rate limit or daily free-tier request quota" in result["response"]


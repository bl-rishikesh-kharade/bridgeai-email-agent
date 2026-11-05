from datetime import datetime, timezone
from app.schemas.email import Email
from app.services.email_signals import EmailSignalEngine
from app.services.chat_service import ChatService
from app.services.email_tools import EmailAgentTools, FilterArgs
from tests.fakes import FakeEmailProvider


def make_email(email_id: str, subject: str, sender: str = "test@example.com", body: str = "Test body", is_read: bool = False, labels: list[str] = None):
    return Email(
        id=email_id,
        provider_message_id=email_id,
        sender=sender,
        receiver="rishikesh.kharade@bridgelabz.com",
        subject=subject,
        body=body,
        is_read=is_read,
        labels=labels or [],
        received_at=datetime.now(timezone.utc),
    )


def test_signal_engine_identifies_critical_security_emails():
    engine = EmailSignalEngine()
    email = make_email("sec-1", "Security alert", sender="no-reply@accounts.google.com", body="New sign-in from Chrome")
    match = engine.evaluate_email(email)

    assert match.priority == "Critical"
    assert match.is_important is True


def test_signal_engine_elevates_user_name_mention_to_high():
    engine = EmailSignalEngine()
    email = make_email("mention-1", "Project Review", sender="colleague@example.com", body="Hi Rishikesh, please review this PR when you have time.")
    match = engine.evaluate_email(email)

    assert match.has_user_mention is True
    assert match.priority == "High"
    assert match.is_important is True


def test_signal_engine_ranks_critical_before_high_before_medium():
    engine = EmailSignalEngine()
    emails = [
        make_email("med-1", "Team status sync", sender="hr@example.com"),
        make_email("crit-1", "Security alert: unauthorized access", sender="no-reply@accounts.google.com"),
        make_email("high-1", "Hostel Fee Notification - Last Date Tomorrow", sender="no-reply@chitkara.edu.in"),
    ]
    ranked = engine.filter_and_rank_emails(emails, only_important=False)

    ids = [item[0].id for item in ranked]
    priorities = [item[1] for item in ranked]

    assert ids == ["crit-1", "high-1", "med-1"]
    assert priorities == ["Critical", "High", "Medium"]


def test_chat_service_clean_card_response_strips_numbered_list():
    raw_response = (
        "Here are 5 recent unread important emails from your inbox:\n\n"
        "1. **Security alert** from `no-reply@accounts.google.com` (Received Nov 5, 2026)\n"
        "2. **New circular – Academic & Hostel Fee Notification...** from `no-reply@chitkara.edu.in` (Received Nov 4, 2026)\n"
        "3. **Security alert** from `no-reply@accounts.google.com` (Received Nov 4, 2026)\n"
    )
    cleaned = ChatService._clean_card_response(raw_response, 3)

    assert "1." not in cleaned
    assert "2." not in cleaned
    assert "3." not in cleaned
    assert "Security alert" not in cleaned
    assert "Here are 5 recent unread important emails from your inbox:" in cleaned


def test_email_tools_hybrid_strategy_uses_signals_first():
    provider = FakeEmailProvider([
        make_email("crit-1", "Security alert", sender="no-reply@accounts.google.com", is_read=False),
        make_email("low-1", "Weekly Newsletter", sender="news@example.com", is_read=False),
    ])
    tools = EmailAgentTools(provider, analyzer=lambda s, b: None)
    outcome = tools.execute("filter_unread_emails", {"filter_id": "important_unread"}, {})

    assert len(outcome.emails) == 1
    assert outcome.emails[0].id == "crit-1"
    assert outcome.data["strategy"] == "signals"
    assert outcome.reviews[0]["priority"] == "Critical"

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


def test_email_tools_signals_strategy_filters_and_ranks():
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


def test_email_tools_gmail_strategy(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "importance_strategy", "gmail")
    provider = FakeEmailProvider([
        make_email("g-1", "Gmail Important Email", sender="boss@example.com", is_read=False, labels=["IMPORTANT"]),
        make_email("g-2", "Ordinary Unread", sender="news@example.com", is_read=False, labels=[]),
    ])
    tools = EmailAgentTools(provider, analyzer=lambda s, b: None)
    outcome = tools.execute("filter_unread_emails", {"filter_id": "important_unread"}, {})

    assert len(outcome.emails) == 1
    assert outcome.emails[0].id == "g-1"
    assert outcome.data["strategy"] == "gmail"


def test_email_tools_candidate_pool_eviction_top_50():
    """Verify that from a 100-email unread pool, critical/high emails are kept and low priority ones are evicted from top 50."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)

    # 10 critical emails, 30 high emails, 60 low newsletters
    pool = []
    for i in range(10):
        pool.append(make_email(f"crit-{i}", f"Security alert {i}", sender="no-reply@accounts.google.com", is_read=False))
    for i in range(30):
        pool.append(make_email(f"high-{i}", f"Academic Fee Notice {i}", sender="no-reply@chitkara.edu.in", is_read=False))
    for i in range(60):
        pool.append(make_email(f"low-{i}", f"Weekly Newsletter {i}", sender="news@example.com", is_read=False))

    provider = FakeEmailProvider(pool)
    tools = EmailAgentTools(provider, analyzer=lambda s, b: None)
    outcome = tools.execute("filter_unread_emails", {"filter_id": "important_unread", "limit": 50}, {})

    # Only important emails should be kept, and top 50 returned
    assert len(outcome.emails) == 40  # 10 critical + 30 high (newsletters filtered out)
    assert outcome.data["pool_size"] == 100
    assert outcome.reviews[0]["priority"] == "Critical"
    assert outcome.reviews[9]["priority"] == "Critical"
    assert outcome.reviews[10]["priority"] == "High"


def test_email_tools_signals_respects_exclude_senders():
    """Verify that when exclude_senders is provided, emails from matching senders or domains are excluded."""
    provider = FakeEmailProvider([
        make_email("sec-1", "Security alert", sender="no-reply@accounts.google.com", is_read=False),
        make_email("chitkara-1", "Hostel Fee Notice", sender="no-reply@chitkara.edu.in", is_read=False),
        make_email("chitkara-2", "Exam Schedule", sender="admin@chitkara.edu.in", is_read=False),
        make_email("bridge-1", "POSH Session", sender="hr@bridgelabz.com", is_read=False),
    ])
    tools = EmailAgentTools(provider, analyzer=lambda s, b: None)
    outcome = tools.execute("filter_unread_emails", {
        "filter_id": "important_unread",
        "exclude_senders": ["chitkara"],
    }, {})

    senders = [str(e.sender) for e in outcome.emails]
    assert len(outcome.emails) == 2
    assert "no-reply@accounts.google.com" in senders
    assert "hr@bridgelabz.com" in senders
    assert not any("chitkara" in s for s in senders)


def test_email_tools_signals_respects_exclude_keywords():
    """Verify that when exclude_keywords is provided (e.g. without circulars), matching emails are omitted."""
    provider = FakeEmailProvider([
        make_email("sec-1", "Security alert", sender="no-reply@accounts.google.com", is_read=False),
        make_email("circ-1", "Academic circular - New grading policy", sender="admin@example.com", is_read=False),
        make_email("fee-1", "Hostel Fee Due Tomorrow", sender="accounts@example.com", is_read=False),
    ])
    tools = EmailAgentTools(provider, analyzer=lambda s, b: None)
    outcome = tools.execute("filter_unread_emails", {
        "filter_id": "important_unread",
        "exclude_keywords": ["circular"],
    }, {})

    subjects = [e.subject for e in outcome.emails]
    assert len(outcome.emails) == 2
    assert "Security alert" in subjects
    assert "Hostel Fee Due Tomorrow" in subjects
    assert not any("circular" in s.lower() for s in subjects)


def test_email_tools_search_unread_only():
    """Verify that search_emails with unread_only=True returns only unread messages."""
    provider = FakeEmailProvider([
        make_email("stipend-1", "Stipend released for October", sender="hr@example.com", is_read=False),
        make_email("stipend-2", "Stipend query resolved", sender="hr@example.com", is_read=True),
    ])
    tools = EmailAgentTools(provider, analyzer=lambda s, b: None)
    outcome = tools.execute("search_emails", {
        "query": "stipend",
        "unread_only": True,
    }, {})

    assert len(outcome.emails) == 1
    assert outcome.emails[0].id == "stipend-1"
    assert outcome.emails[0].is_read is False




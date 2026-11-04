from tests.fakes import FakeEmailProvider
from app.schemas.email import Email


def test_email_provider():
    provider = FakeEmailProvider([Email(
        id="1", provider_message_id="1", sender="a@example.com",
        receiver="b@example.com", subject="Hello", body="Body"
    )])
    assert provider.get_email("1").subject == "Hello"
    assert len(provider.list_emails()) == 1

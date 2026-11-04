from app.services.chat_service import build_chat_service
from tests.fakes import FakeEmailProvider


def test_chat_service_can_be_constructed_with_providers():
    service = build_chat_service(FakeEmailProvider())
    assert service is not None

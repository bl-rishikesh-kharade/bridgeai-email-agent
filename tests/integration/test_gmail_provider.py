import base64

import pytest

from app.integrations.email.gmail_provider import GmailEmailProvider, GmailProviderError


def encoded(text):
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def message(mid="abc"):
    return {
        "id": mid,
        "internalDate": "1760000000000",
        "labelIds": ["INBOX", "UNREAD"],
        "payload": {
            "headers": [
                {"name": "From", "value": "Sender <sender@example.com>"},
                {"name": "To", "value": "Receiver <receiver@example.com>"},
                {"name": "Subject", "value": "Hello"},
            ],
            "mimeType": "multipart/alternative",
            "parts": [
                {"mimeType": "text/plain", "body": {"data": encoded("Plain body")}},
                {"mimeType": "text/html", "body": {"data": encoded("<p>HTML</p>")}},
            ],
        },
    }


class Request:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    def execute(self):
        if self.error:
            raise self.error
        return self.result


class Messages:
    def __init__(self, listing=None, gets=None):
        self.listing, self.gets = listing, gets or {}

    def list(self, **kwargs):
        return Request(self.listing)

    def get(self, userId, id, format):
        return self.gets.get(id, Request(error=NotFound()))


class NotFound(Exception):
    class Response:
        status = 404

    resp = Response()


class Users:
    def __init__(self, messages):
        self._messages = messages

    def messages(self):
        return self._messages


class Service:
    def __init__(self, messages):
        self._users = Users(messages)

    def users(self):
        return self._users


def test_maps_headers_multipart_body_and_read_state():
    email = GmailEmailProvider.map_message(message())
    assert email.id == "abc"
    assert email.sender == "sender@example.com"
    assert email.receiver == "receiver@example.com"
    assert email.body == "Plain body"
    assert email.is_read is False
    assert "INBOX" in email.labels
    assert email.received_at is not None


def test_exact_id_and_not_found():
    provider = GmailEmailProvider(Service(Messages(gets={"abc": Request(message("abc"))})))
    assert provider.get_email("abc").id == "abc"
    assert provider.get_email("other") is None


def test_list_pages_and_respects_limit():
    refs = [{"id": "a"}, {"id": "b"}]
    messages = Messages(listing={"messages": refs}, gets={
        "a": Request(message("a")), "b": Request(message("b")),
    })
    assert [m.id for m in GmailEmailProvider(Service(messages)).list_emails(2)] == ["a", "b"]


def test_list_follows_next_page_token():
    class PagedMessages(Messages):
        def __init__(self):
            self.calls = []

        def list(self, **kwargs):
            self.calls.append(kwargs.get("pageToken"))
            if kwargs.get("pageToken") is None:
                return Request({"messages": [{"id": "a"}], "nextPageToken": "next"})
            return Request({"messages": [{"id": "b"}]})

    messages = PagedMessages()
    messages.gets = {"a": Request(message("a")), "b": Request(message("b"))}
    emails = GmailEmailProvider(Service(messages)).list_emails(2)
    assert [email.id for email in emails] == ["a", "b"]
    assert messages.calls == [None, "next"]


def test_important_unread_filter_uses_gmail_system_labels():
    class QueryMessages(Messages):
        def __init__(self):
            self.labels = None

        def list(self, **kwargs):
            self.labels = kwargs.get("labelIds")
            return Request({"messages": []})

    messages = QueryMessages()
    GmailEmailProvider(Service(messages)).list_filtered_emails("important_unread")
    assert messages.labels == ["UNREAD", "IMPORTANT"]


def test_search_emails_builds_sender_or_full_text_search():
    class QueryMessages(Messages):
        def __init__(self):
            self.query = None

        def list(self, **kwargs):
            self.query = kwargs.get("q")
            return Request({"messages": []})

    messages = QueryMessages()
    provider = GmailEmailProvider(Service(messages))
    assert provider.search_emails("HOPR", sender_only=True) == []
    assert messages.query == 'from:"HOPR"'
    assert provider.search_emails("FA_2 Product Data", sender_only=False) == []
    assert messages.query == '"FA_2 Product Data"'


def test_rejects_malformed_messages_and_exposes_no_email_write_operations():
    with pytest.raises(GmailProviderError):
        GmailEmailProvider.map_message({})
    provider = GmailEmailProvider(Service(Messages()))
    assert not hasattr(provider, "mark_as_read")
    assert not hasattr(provider, "create_email")


def test_provider_errors_are_sanitized():
    messages = Messages(gets={"abc": Request(error=RuntimeError("private provider detail"))})
    provider = GmailEmailProvider(Service(messages))
    with pytest.raises(GmailProviderError, match="retrieval failed") as error:
        provider.get_email("abc")
    assert "private provider detail" not in str(error.value)

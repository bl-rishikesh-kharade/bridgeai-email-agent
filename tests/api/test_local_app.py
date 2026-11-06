from fastapi.testclient import TestClient

from app.main import app


def test_local_ui_and_health_do_not_need_google_authorization():
    with TestClient(app) as client:
        page = client.get("/")
        health = client.get("/health")
        removed_user_route = client.get("/users")
    assert page.status_code == 200
    assert "BridgeAI Email Agent" in page.text
    assert 'id="root"' in page.text
    assert health.status_code == 200
    assert "x-request-id" not in health.headers
    assert removed_user_route.status_code == 404


def test_built_react_assets_are_served_by_the_local_app():
    with TestClient(app) as client:
        page = client.get("/")
        script_path = next(part.split('src="', 1)[1].split('"', 1)[0]
                           for part in page.text.split() if part.startswith("src=\"/assets/"))
        script = client.get(script_path)
    assert script.status_code == 200
    assert "Email Agent" in script.text
    assert "Runs on this computer" not in script.text


def test_agent_chat_rejects_unknown_filter_ids():
    with TestClient(app) as client:
        response = client.post("/agent/chat", json={
            "message": "Do something", "filter_id": "delete_all_emails",
        })
    assert response.status_code == 422


def test_auth_status_and_disconnect_routes():
    from fastapi import FastAPI
    from app.api.routes.auth import build_router as build_auth_router
    from tests.fakes import FakeEmailProvider

    class FakeOAuth:
        def __init__(self, connected=True):
            self._connected = connected

        def has_saved_authorization(self):
            return self._connected

        def disconnect(self):
            self._connected = False

    fake_oauth = FakeOAuth(connected=True)
    fake_provider = FakeEmailProvider()
    test_app = FastAPI()
    test_app.include_router(build_auth_router(fake_oauth, fake_provider))

    with TestClient(test_app) as client:
        status_res = client.get("/auth/status")
        assert status_res.status_code == 200
        assert status_res.json() == {"connected": True, "email": "user@example.com"}

        disconnect_res = client.post("/auth/disconnect")
        assert disconnect_res.status_code == 200
        assert disconnect_res.json() == {"connected": False, "email": None}

        status_after = client.get("/auth/status")
        assert status_after.status_code == 200
        assert status_after.json() == {"connected": False, "email": None}


def test_agent_chat_important_unread_workflow():
    from fastapi import FastAPI
    from app.api.routes.agent import build_router as build_agent_router
    from app.schemas.email import Email
    from app.services.chat_service import build_chat_service
    from tests.fakes import FakeEmailProvider

    email = Email(
        id="imp-1", provider_message_id="imp-1", sender="boss@example.com",
        receiver="user@example.com", subject="Urgent matter", body="Please review immediately",
        is_read=False, labels=["IMPORTANT"],
    )
    fake_provider = FakeEmailProvider([email])
    chat_service = build_chat_service(fake_provider)
    test_app = FastAPI()
    test_app.include_router(build_agent_router(chat_service, fake_provider))

    with TestClient(test_app) as client:
        response = client.post("/agent/chat", json={
            "message": "Show my unread important emails",
            "filter_id": "important_unread",
        })
        assert response.status_code == 200
        data = response.json()
        assert "Found 1 unread important email" in data["response"]
        assert len(data["email_options"]) == 1
        assert data["email_options"][0]["id"] == "imp-1"
        assert data["email_options"][0]["subject"] == "Urgent matter"
        assert "mail.google.com" in data["email_options"][0]["gmail_url"]


def test_agent_chat_accepts_history_buffer():
    from fastapi import FastAPI
    from app.api.routes.agent import build_router as build_agent_router
    from app.services.chat_service import build_chat_service
    from tests.fakes import FakeEmailProvider

    captured = []

    def mock_model_turn(messages, tool_declarations, system_instruction, **kwargs):
        captured.extend(messages)
        return type("Turn", (), {"text": "History received", "tool_calls": [], "model_content": None})()

    fake_provider = FakeEmailProvider()
    chat_service = build_chat_service(fake_provider, model_turn=mock_model_turn)
    test_app = FastAPI()
    test_app.include_router(build_agent_router(chat_service, fake_provider))

    with TestClient(test_app) as client:
        response = client.post("/agent/chat", json={
            "message": "What did I ask before?",
            "history": [
                {"role": "user", "text": "Can you check my inbox?"},
                {"role": "assistant", "text": "I found 2 emails."},
            ],
        })
        assert response.status_code == 200
        assert response.json()["response"] == "History received"
        assert len(captured) == 3
        assert captured[0].role == "user"
        assert captured[1].role == "model"
        assert captured[2].role == "user"


def test_vercel_serverless_entrypoint():
    import api.index
    assert api.index.app is not None
    assert api.index.app.title == "BridgeAI Email Agent"


def test_auth_session_cookie_handling():
    import json
    from fastapi import FastAPI
    from app.api.routes.auth import build_router as build_auth_router
    from tests.fakes import FakeEmailProvider

    class FakeOAuth:
        def __init__(self):
            self.redirect_urls = []

        def has_saved_authorization(self):
            return False

        def get_authorization_url(self, redirect_uri):
            self.redirect_urls.append(redirect_uri)
            return f"https://accounts.google.com/o/oauth2/v2/auth?redirect_uri={redirect_uri}", "verifier-123"

        def exchange_code_for_token(self, code, redirect_uri, code_verifier=None):
            return {"token": "test-token"}

        def credentials_from_token(self, token_data):
            return token_data

        def service(self, name, version, creds=None):
            return None

        def disconnect(self):
            pass

    fake_oauth = FakeOAuth()
    fake_provider = FakeEmailProvider()
    test_app = FastAPI()
    test_app.include_router(build_auth_router(fake_oauth, fake_provider))

    with TestClient(test_app) as client:
        # 1. Unauthenticated
        res = client.get("/auth/status")
        assert res.json() == {"connected": False, "email": None}

        # 2. Login initiates redirect
        login_res = client.get("/auth/login", follow_redirects=False)
        assert login_res.status_code == 307
        assert "accounts.google.com" in login_res.headers["location"]

        # 3. Callback sets session cookie with user email
        cb_res = client.get("/auth/callback?code=fake-auth-code", follow_redirects=False)
        assert cb_res.status_code == 303
        assert "bridgeai_session_token" in cb_res.headers.get("set-cookie", "")

        # 4. Status with session cookie returns connected and user email
        status_res = client.get("/auth/status")
        assert status_res.status_code == 200
        assert status_res.json()["connected"] is True
        assert status_res.json()["email"] == "user@example.com"

        # 5. Disconnect clears cookie
        disco_res = client.post("/auth/disconnect")
        assert disco_res.status_code == 200
        assert "bridgeai_session_token" in disco_res.headers.get("set-cookie", "")

        # 6. Status after disconnect is cleanly disconnected
        final_res = client.get("/auth/status")
        assert final_res.json() == {"connected": False, "email": None}


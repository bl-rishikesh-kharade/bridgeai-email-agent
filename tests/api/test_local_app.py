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

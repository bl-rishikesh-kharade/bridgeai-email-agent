from pathlib import Path
import pytest

from app.integrations.google.oauth import GoogleOAuthError, GoogleOAuthManager
from app.core.config import Settings


def test_oauth_is_lazy_and_reports_missing_client_safely():
    settings = Settings(oauth_credentials_path="credentials/does-not-exist.json",
                        oauth_token_path=".oauth-test-token.json")
    manager = GoogleOAuthManager(settings)
    assert manager._credentials is None
    with pytest.raises(GoogleOAuthError, match="OAuth client file not found"):
        manager.credentials()
    assert not Path(settings.oauth_token_path).exists()


def test_credentials_from_token_constructs_valid_credentials():
    settings = Settings(google_client_id="test-cid", google_client_secret="test-sec")
    manager = GoogleOAuthManager(settings)
    token_dict = {
        "token": "mock-access-token",
        "scopes": ["https://www.googleapis.com/auth/gmail.readonly"],
    }
    creds = manager.credentials_from_token(token_dict)
    assert creds is not None
    assert creds.valid
    assert creds.client_id == "test-cid"


def test_disconnect_safe_when_token_file_missing():
    settings = Settings(oauth_token_path=".non-existent-token.json")
    manager = GoogleOAuthManager(settings)
    # Should complete cleanly without raising GoogleOAuthError or OSError
    manager.disconnect()
    assert manager._credentials is None


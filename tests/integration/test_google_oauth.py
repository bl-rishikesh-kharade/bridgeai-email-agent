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

"""Local, single-user Google OAuth with an explicit connect action."""
from pathlib import Path
import json
import threading


class GoogleOAuthError(RuntimeError):
    """Safe error for missing or invalid local Google authorization."""


class GoogleOAuthManager:
    def __init__(self, settings):
        self.credentials_path = Path(settings.oauth_credentials_path)
        self.token_path = Path(settings.oauth_token_path)
        self.client_id = settings.google_client_id
        self.client_secret = settings.google_client_secret
        self.redirect_uri = settings.google_redirect_uri
        self.scopes = list(settings.oauth_scopes)
        self.timeout = settings.request_timeout
        self._credentials = None
        self._lock = threading.Lock()

    def get_client_config(self) -> dict:
        """Return OAuth client config from file or environment variables."""
        if self.client_id and self.client_secret:
            return {
                "web": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            }
        if self.credentials_path.is_file():
            data = json.loads(self.credentials_path.read_text(encoding="utf-8"))
            return data
        raise GoogleOAuthError(f"OAuth client file not found: {self.credentials_path}")

    def get_authorization_url(self, redirect_uri: str, state: str | None = None) -> str:
        """Build Google web authorization redirect URL."""
        from google_auth_oauthlib.flow import Flow
        client_config = self.get_client_config()
        flow = Flow.from_client_config(client_config, scopes=self.scopes, redirect_uri=redirect_uri)
        auth_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="select_account",
            state=state,
        )
        return auth_url

    def exchange_code_for_token(self, code: str, redirect_uri: str) -> dict:
        """Exchange Google authorization code for token dictionary."""
        from google_auth_oauthlib.flow import Flow
        client_config = self.get_client_config()
        flow = Flow.from_client_config(client_config, scopes=self.scopes, redirect_uri=redirect_uri)
        flow.fetch_token(code=code)
        creds = flow.credentials
        return json.loads(creds.to_json())

    def credentials_from_token(self, token_data: dict | str):
        """Build Google Credentials object from token dictionary or JSON string."""
        from google.oauth2.credentials import Credentials
        if isinstance(token_data, str):
            token_data = json.loads(token_data)
        return Credentials.from_authorized_user_info(token_data, self.scopes)

    def credentials(self):
        if self._credentials and self._credentials.valid and self._credentials.has_scopes(self.scopes):
            return self._credentials
        with self._lock:
            if self._credentials and self._credentials.valid and self._credentials.has_scopes(self.scopes):
                return self._credentials
            self._credentials = self._load_saved_credentials()
            if self._credentials is None:
                raise GoogleOAuthError("Google is not connected. Choose Connect Google to authorize this account.")
            return self._credentials

    def connect(self):
        """Run the installed-app OAuth flow after the user presses Connect Google."""
        if not self.credentials_path.is_file():
            raise GoogleOAuthError(f"OAuth client file not found: {self.credentials_path}")
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
        except ImportError as exc:
            raise GoogleOAuthError("Install Google OAuth dependencies from requirements.txt.") from exc
        try:
            flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), self.scopes)
            credentials = flow.run_local_server(port=0, prompt="select_account")
            with self._lock:
                self._save_credentials(credentials)
                self._credentials = credentials
            return credentials
        except GoogleOAuthError:
            raise
        except Exception as exc:
            raise GoogleOAuthError("Google authorization failed; confirm the Workspace account and requested permissions.") from exc

    def has_saved_authorization(self) -> bool:
        """Return whether reusable Gmail credentials are available locally."""
        with self._lock:
            try:
                self._credentials = self._load_saved_credentials()
                return self._credentials is not None
            except GoogleOAuthError:
                return False

    def disconnect(self) -> None:
        """Clear the locally saved Google authorization so another account can connect."""
        with self._lock:
            self._credentials = None
            try:
                self.token_path.unlink(missing_ok=True)
            except OSError as exc:
                raise GoogleOAuthError("Saved Google authorization could not be cleared.") from exc

    def _load_saved_credentials(self):
        if not self.credentials_path.is_file():
            raise GoogleOAuthError(f"OAuth client file not found: {self.credentials_path}")
        if not self.token_path.is_file():
            return None
        try:
            from google.auth.transport.requests import Request
            from google.auth.exceptions import RefreshError
            from google.oauth2.credentials import Credentials

            stored_scopes = json.loads(self.token_path.read_text(encoding="utf-8")).get("scopes", [])
            if not set(self.scopes).issubset(set(stored_scopes)):
                return None
            credentials = Credentials.from_authorized_user_file(str(self.token_path), self.scopes)
            if credentials.has_scopes(self.scopes) and credentials.valid:
                return credentials
            if credentials.expired and credentials.refresh_token:
                try:
                    credentials.refresh(Request())
                except RefreshError:
                    return None
                self._save_credentials(credentials)
                return credentials if credentials.valid and credentials.has_scopes(self.scopes) else None
            return None
        except GoogleOAuthError:
            raise
        except Exception as exc:
            raise GoogleOAuthError("Saved Google authorization could not be loaded. Choose Connect Google to reconnect.") from exc

    def _save_credentials(self, credentials):
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(credentials.to_json(), encoding="utf-8")
        try:
            self.token_path.chmod(0o600)
        except OSError:
            pass

    def service(self, api: str, version: str, creds=None):
        try:
            from google_auth_httplib2 import AuthorizedHttp
            from googleapiclient.discovery import build
            import httplib2
            credentials = creds or self.credentials()
            http = AuthorizedHttp(credentials, http=httplib2.Http(timeout=self.timeout))
            return build(api, version, http=http, cache_discovery=False)
        except GoogleOAuthError:
            raise
        except Exception as exc:
            raise GoogleOAuthError("Google service could not be initialized.") from exc

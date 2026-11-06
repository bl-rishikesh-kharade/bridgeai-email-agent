import json
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.integrations.google.oauth import GoogleOAuthError
from app.integrations.email.gmail_provider import GmailEmailProvider, GmailProviderError


def build_router(oauth_manager, email_provider):
    router = APIRouter(prefix="/auth", tags=["auth"])

    def _resolve_session_provider(request: Request):
        """Build provider from session cookie if present, else fallback to default provider."""
        auth_cookie = request.cookies.get("bridgeai_session_token")
        if auth_cookie:
            try:
                token_data = json.loads(auth_cookie)
                creds = oauth_manager.credentials_from_token(token_data)
                return GmailEmailProvider(service_factory=lambda: oauth_manager.service("gmail", "v1", creds=creds))
            except Exception:
                pass
        return email_provider

    @router.get("/status")
    def status(request: Request):
        # 1. Check browser session cookie (Web / Vercel mode)
        auth_cookie = request.cookies.get("bridgeai_session_token")
        if auth_cookie:
            try:
                session_provider = _resolve_session_provider(request)
                return {"connected": True, "email": session_provider.get_account_email()}
            except Exception:
                pass

        # 2. Check local saved authorization (Local Desktop mode)
        if not oauth_manager.has_saved_authorization():
            return {"connected": False, "email": None}
        try:
            return {"connected": True, "email": email_provider.get_account_email()}
        except (GoogleOAuthError, GmailProviderError):
            return {"connected": False, "email": None}

    @router.get("/login")
    def login(request: Request):
        """Initiate Web OAuth redirect (used in cloud/Vercel environments)."""
        redirect_uri = settings.google_redirect_uri or str(request.url_for("auth_callback"))
        # Ensure https scheme when behind cloud reverse proxies (e.g. Vercel)
        if "vercel.app" in redirect_uri and redirect_uri.startswith("http://"):
            redirect_uri = redirect_uri.replace("http://", "https://", 1)
        try:
            auth_url = oauth_manager.get_authorization_url(redirect_uri)
            return RedirectResponse(auth_url)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to generate authorization URL: {exc}") from exc

    @router.get("/callback", name="auth_callback")
    def callback(code: str, request: Request):
        """Receive Google OAuth callback, store token in session cookie, and redirect to home."""
        redirect_uri = settings.google_redirect_uri or str(request.url_for("auth_callback"))
        if "vercel.app" in redirect_uri and redirect_uri.startswith("http://"):
            redirect_uri = redirect_uri.replace("http://", "https://", 1)
        try:
            token_dict = oauth_manager.exchange_code_for_token(code, redirect_uri)
            response = RedirectResponse(url="/")
            # Set httpOnly session cookie with the user's token
            response.set_cookie(
                key="bridgeai_session_token",
                value=json.dumps(token_dict),
                httponly=True,
                samesite="lax",
                secure=request.url.scheme == "https" or "vercel.app" in str(request.base_url),
                max_age=60 * 60 * 24 * 7,  # 7 days
            )
            return response
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"OAuth authorization failed: {exc}") from exc

    @router.post("/connect")
    def connect(request: Request):
        """Connect Gmail: if in web mode with client ID, return redirect; otherwise run local desktop server."""
        if settings.google_client_id and settings.google_client_secret:
            # Signal frontend to redirect to /auth/login
            return {"connected": False, "redirect": "/auth/login"}
        try:
            oauth_manager.connect()
            return {"connected": True, "email": email_provider.get_account_email()}
        except (GoogleOAuthError, GmailProviderError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.post("/disconnect")
    def disconnect(response: Response):
        """Disconnect and clear both session cookies and local authorization."""
        response.delete_cookie("bridgeai_session_token")
        try:
            oauth_manager.disconnect()
            email_provider.reset_connection()
            return {"connected": False, "email": None}
        except GoogleOAuthError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return router

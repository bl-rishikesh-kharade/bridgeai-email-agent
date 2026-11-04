from fastapi import APIRouter, HTTPException

from app.integrations.google.oauth import GoogleOAuthError
from app.integrations.email.gmail_provider import GmailProviderError


def build_router(oauth_manager, email_provider):
    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.get("/status")
    def status():
        if not oauth_manager.has_saved_authorization():
            return {"connected": False, "email": None}
        try:
            return {"connected": True, "email": email_provider.get_account_email()}
        except GmailProviderError as exc:
            raise HTTPException(status_code=503, detail="The connected Google account could not be checked. Try again.") from exc

    @router.post("/connect")
    def connect():
        try:
            oauth_manager.connect()
            return {"connected": True, "email": email_provider.get_account_email()}
        except (GoogleOAuthError, GmailProviderError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return router

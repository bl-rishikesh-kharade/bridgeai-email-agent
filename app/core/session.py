"""Session token encoding, decoding, and cookie management utility.

Adheres to Single Responsibility Principle (SRP) and DRY by centralizing
OAuth session token serialization, deserialization, and HTTP response cookie syncing.
"""
import base64
import json
import logging
from typing import Any
from fastapi import Request, Response

from app.integrations.email.gmail_provider import GmailEmailProvider

logger = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "bridgeai_session_token"
SESSION_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def encode_session_token(token_data: dict[str, Any]) -> str:
    """Encode token dictionary into a URL-safe base64 string."""
    raw = json.dumps(token_data).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_session_token(cookie_str: str | None) -> dict[str, Any] | None:
    """Safely decode session cookie string back to dictionary."""
    if not cookie_str:
        return None
    try:
        if cookie_str.startswith("{"):
            return json.loads(cookie_str)
        padding = 4 - (len(cookie_str) % 4)
        if padding != 4:
            cookie_str += "=" * padding
        raw = base64.urlsafe_b64decode(cookie_str.encode("ascii"))
        return json.loads(raw.decode("utf-8"))
    except Exception:
        logger.debug("Failed to decode session cookie", exc_info=True)
        return None


def is_https_request(request: Request) -> bool:
    """Detect if incoming request is over HTTPS or behind an HTTPS proxy (e.g. Vercel)."""
    return (
        request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto") == "https"
        or "vercel.app" in str(request.base_url)
    )


def set_session_cookie(response: Response, token_data: dict[str, Any], request: Request) -> None:
    """Persist session token cookie to HTTP response with 30-day lifespan."""
    is_https = is_https_request(request)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=encode_session_token(token_data),
        httponly=True,
        samesite="lax",
        secure=is_https,
        max_age=SESSION_COOKIE_MAX_AGE,
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    """Clear session cookie from response."""
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")


def resolve_session_provider(
    request: Request,
    response: Response | None,
    oauth_manager: Any,
    fallback_provider: Any,
) -> tuple[Any, bool]:
    """
    Resolve active Gmail provider for the current request.
    
    If token is expired, proactively uses the refresh token to silently obtain
    a new access token from Google, and updates the session cookie on the response.
    Returns (provider, token_was_refreshed).
    """
    if not oauth_manager:
        return fallback_provider, False

    auth_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not auth_cookie:
        return fallback_provider, False

    token_data = decode_session_token(auth_cookie)
    if not token_data:
        return fallback_provider, False

    try:
        orig_token = token_data.get("token") or token_data.get("access_token")
        # credentials_from_token will automatically refresh via refresh_token if expired
        creds = oauth_manager.credentials_from_token(token_data)
        refreshed = token_data.get("token") != orig_token

        # If token was refreshed and response object is provided, sync new token back to cookie
        if refreshed and response is not None:
            set_session_cookie(response, token_data, request)

        provider = GmailEmailProvider(
            service_factory=lambda: oauth_manager.service("gmail", "v1", creds=creds),
            oauth_manager=oauth_manager,
        )
        return provider, refreshed
    except Exception:
        logger.debug("Silent session token resolution failed", exc_info=True)
        return fallback_provider, False

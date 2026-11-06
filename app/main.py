from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.api.routes.auth import build_router as build_auth_router
from app.api.routes.agent import build_router as build_agent_router
from app.api.routes.health import router as health_router
from app.core.config import settings
from app.core.logger import log_event
from app.integrations.email.gmail_provider import GmailEmailProvider, GmailProviderError
from app.integrations.google.oauth import GoogleOAuthManager
from app.services.chat_service import build_chat_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_event("application.started", environment=settings.environment)
    yield
    log_event("application.stopped", environment=settings.environment)


def create_app():
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="A local Gmail assistant with a focused unread-important workflow.",
        lifespan=lifespan,
    )

    @app.exception_handler(GmailProviderError)
    async def gmail_provider_error(_request: Request, _exc: GmailProviderError):
        return JSONResponse(status_code=503, content={"detail": "Email provider is unavailable or not authorized."})

    oauth = GoogleOAuthManager(settings)
    email_provider = GmailEmailProvider.from_settings(settings, oauth)
    chat_service = build_chat_service(email_provider)

    app.include_router(health_router)
    app.include_router(build_auth_router(oauth, email_provider))
    app.include_router(build_agent_router(chat_service, email_provider, oauth_manager=oauth))

    static_dir = Path(__file__).parent / "static"
    react_ui_dir = static_dir / "react-ui"
    if (react_ui_dir / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=react_ui_dir / "assets"), name="frontend-assets")

    @app.get("/", include_in_schema=False)
    def home():
        react_index = react_ui_dir / "index.html"
        return FileResponse(react_index if react_index.is_file() else static_dir / "index.html")

    return app


app = create_app()

import uvicorn
from app.core.config import settings


def main():
    is_dev = settings.environment != "production"
    uvicorn.run("app.main:app", host="127.0.0.1", port=settings.app_port, reload=is_dev)


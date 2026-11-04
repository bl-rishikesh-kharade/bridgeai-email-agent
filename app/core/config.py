from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application
    app_name: str = "BridgeAI Email Agent"
    app_version: str = "2.0.0"
    app_port: int = Field(default=8000, ge=1024, le=65535)
    environment: Literal["development", "test", "production"] = "development"

    # Logging
    log_level: str = "INFO"
    log_file_path: str | None = None

    # Gemini
    gemini_api_key: str | None = None
    gemini_model: str = Field(default="gemini-3.6-flash", min_length=1, max_length=100)
    gemini_temperature: float = Field(default=0.1, ge=0, le=2)

    # OAuth
    oauth_credentials_path: str = "credentials/credentials.json"
    oauth_token_path: str = "token.json"
    oauth_scopes: list[str] = [
        "https://www.googleapis.com/auth/gmail.readonly",
    ]

    # Timeouts (seconds)
    request_timeout: float = Field(default=30.0, gt=0, le=120)
    gemini_timeout: float = Field(default=60.0, gt=0, le=300)
    max_email_body_chars: int = Field(default=30000, ge=1000, le=100000)
    # Limits
    max_email_list_limit: int = Field(default=100, ge=1, le=500)
    default_email_list_limit: int = Field(default=50, ge=1, le=100)

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL.")
        return normalized

    @model_validator(mode="after")
    def validate_production_configuration(self):
        if self.environment == "production":
            if not self.gemini_api_key or not self.gemini_api_key.strip():
                raise ValueError("Production requires GEMINI_API_KEY.")
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

settings = Settings()

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_requires_gemini_configuration():
    with pytest.raises(ValidationError, match="GEMINI_API_KEY or GROQ_API_KEY"):
        Settings(_env_file=None, environment="production", gemini_api_key=None, groq_api_key=None)


def test_local_production_configuration_is_accepted():
    settings = Settings(
        _env_file=None,
        environment="production",
        gemini_api_key="test-key",
    )
    assert settings.environment == "production"


def test_configuration_rejects_invalid_limits_and_log_level():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, request_timeout=0)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, gemini_temperature=2.1)
    with pytest.raises(ValidationError, match="LOG_LEVEL"):
        Settings(_env_file=None, log_level="verbose")


def test_log_level_is_normalized():
    assert Settings(_env_file=None, log_level="debug").log_level == "DEBUG"

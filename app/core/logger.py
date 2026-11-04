"""Structured application logs with a local rotating file and console output."""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from app.core.config import settings


_SAFE_FIELDS = (
    "event", "step", "operation", "duration_ms",
    "result_count", "error_type", "status_code", "api_status", "model",
    "environment",
    "log_file", "tool_name", "reason",
    "cause_type", "winerror", "errno",
)


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in _SAFE_FIELDS:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


def log_event(event: str, *, level: int = logging.INFO, **fields: Any) -> None:
    """Write only explicitly supplied, non-sensitive operational fields."""
    logger.log(level, event, extra={"event": event, **fields})


def _default_log_path() -> Path:
    if settings.log_file_path:
        return Path(settings.log_file_path).expanduser()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Logs"
    else:
        base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "BridgeAI Email Agent" / "logs" / "bridgeai.log"


logger = logging.getLogger("bridgeai")
logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
logger.propagate = False

if not logger.handlers:
    formatter = _JsonFormatter()
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)
    try:
        log_path = _default_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path, maxBytes=5 * 1024 * 1024, backupCount=4, encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        log_event("logging.file.enabled", log_file=str(log_path))
    except OSError as exc:
        logger.warning("Persistent log file unavailable; continuing with console logging (error_type=%s)", type(exc).__name__)

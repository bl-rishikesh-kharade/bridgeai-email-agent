import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.core.logger import log_event
from app.schemas.email import Email

logger = logging.getLogger("bridgeai")

DEFAULT_SIGNALS_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "signals.json"

PriorityLevel = Literal["Critical", "High", "Medium", "Low"]

PRIORITY_RANKS: dict[str, int] = {
    "Critical": 4,
    "High": 3,
    "Medium": 2,
    "Low": 1,
}


@dataclass
class EmailSignalMatch:
    email: Email
    priority: PriorityLevel
    matched_signals: list[str]
    has_user_mention: bool
    is_important: bool


class EmailSignalEngine:
    def __init__(self, config_path: Path | str | None = None):
        self.config_path = Path(config_path) if config_path else DEFAULT_SIGNALS_PATH
        self._cached_config: dict[str, Any] | None = None
        self._last_mtime: float = 0

    def load_config(self) -> dict[str, Any]:
        """Load signals config from disk, reloading automatically if the file has changed."""
        if self.config_path.is_file():
            try:
                mtime = self.config_path.stat().st_mtime
                if self._cached_config is None or mtime != self._last_mtime:
                    with open(self.config_path, "r", encoding="utf-8") as f:
                        self._cached_config = json.load(f)
                    self._last_mtime = mtime
                return self._cached_config
            except Exception as exc:
                logger.warning("Failed to load signals config from %s: %s", self.config_path, exc)
        return self._default_config()

    @staticmethod
    def _default_config() -> dict[str, Any]:
        return {
            "user_name": "Rishikesh",
            "user_emails": ["rishikesh.kharade@bridgelabz.com"],
            "importance_strategy": "hybrid",
            "signals": {
                "critical": {
                    "sender_keywords": ["accounts.google.com", "security", "alert"],
                    "subject_keywords": ["security alert", "critical", "urgent"],
                    "body_keywords": ["security alert", "unrecognized device", "password reset"],
                },
                "high": {
                    "subject_keywords": ["fee", "st-ii", "rubrics", "evaluation", "deadline", "circular"],
                    "body_keywords": ["due date", "last date", "mandatory", "action required"],
                },
                "medium": {
                    "subject_keywords": ["update", "circular", "announcement", "meeting"],
                    "body_keywords": ["fyi", "reminder"],
                },
                "low": {
                    "subject_keywords": ["newsletter", "digest", "promotional"],
                    "body_keywords": ["unsubscribe"],
                },
            },
        }

    @staticmethod
    def _matches_keyword(kw: str, sender: str, subject: str, body: str) -> bool:
        kw = kw.strip().casefold()
        if not kw:
            return False
        # If keyword looks like a domain or email address (contains @ or .)
        if "@" in kw or "." in kw:
            return kw in sender or kw in subject or kw in body
        # For general words/phrases, use word boundary regex to avoid partial word matches (e.g. 'exam' in 'example.com', 'fee' in 'coffee')
        pattern = rf"\b{re.escape(kw)}\b"
        return bool(
            re.search(pattern, subject)
            or re.search(pattern, body)
            or re.search(pattern, sender)
        )

    def evaluate_email(self, email: Email) -> EmailSignalMatch:
        """Evaluate a single email against the configured text signals and user mentions."""
        config = self.load_config()
        user_name = str(config.get("user_name", "")).strip().casefold()
        rules = config.get("priority_rules") or {}

        subject = email.subject.casefold()
        body = email.body.casefold()
        sender = email.sender.casefold()

        # Check for explicit user name mention in body or subject (as per technical specification requirement)
        has_user_mention = bool(
            user_name
            and (
                re.search(rf"\b{re.escape(user_name)}\b", body)
                or re.search(rf"\b{re.escape(user_name)}\b", subject)
            )
        )

        # 1. Critical Check
        critical_kws = rules.get("critical", ["security alert", "unrecognized device", "critical"])
        if any(self._matches_keyword(kw, sender, subject, body) for kw in critical_kws):
            return EmailSignalMatch(
                email=email,
                priority="Critical",
                matched_signals=["critical.rule"],
                has_user_mention=has_user_mention,
                is_important=True,
            )

        # 2. User name mention explicitly elevates to High
        if has_user_mention:
            return EmailSignalMatch(
                email=email,
                priority="High",
                matched_signals=["user.name_mention"],
                has_user_mention=True,
                is_important=True,
            )

        # 3. High Check
        high_kws = rules.get("high", ["fee", "st-ii", "rubrics", "evaluation", "deadline"])
        if any(self._matches_keyword(kw, sender, subject, body) for kw in high_kws):
            return EmailSignalMatch(
                email=email,
                priority="High",
                matched_signals=["high.rule"],
                has_user_mention=has_user_mention,
                is_important=True,
            )

        # 4. Low Check
        low_kws = rules.get("low", ["newsletter", "digest", "promotional", "unsubscribe"])
        if any(self._matches_keyword(kw, sender, subject, body) for kw in low_kws):
            return EmailSignalMatch(
                email=email,
                priority="Low",
                matched_signals=["low.rule"],
                has_user_mention=False,
                is_important=False,
            )

        # 5. Medium Check
        medium_kws = rules.get("medium", ["update", "meeting", "sync"])
        if any(self._matches_keyword(kw, sender, subject, body) for kw in medium_kws):
            return EmailSignalMatch(
                email=email,
                priority="Medium",
                matched_signals=["medium.rule"],
                has_user_mention=False,
                is_important=False,
            )

        # Default priority
        return EmailSignalMatch(
            email=email,
            priority="Medium",
            matched_signals=["default"],
            has_user_mention=False,
            is_important=False,
        )

    def filter_and_rank_emails(
        self,
        emails: list[Email],
        *,
        only_important: bool = True,
        limit: int = 10,
    ) -> list[tuple[Email, PriorityLevel]]:
        """Filter emails by importance signals and sort them by Priority (Critical first)."""
        evaluated = [self.evaluate_email(email) for email in emails]

        if only_important:
            candidates = [m for m in evaluated if m.is_important]
        else:
            candidates = evaluated

        # Sort: Highest priority rank first (Critical=4, High=3, Medium=2, Low=1),
        # followed by newest received_at for ties
        def sort_key(match: EmailSignalMatch):
            rank = PRIORITY_RANKS.get(match.priority, 1)
            # Use timestamp as secondary key; fallback to 0 if None
            ts = match.email.received_at.timestamp() if match.email.received_at else 0
            return (rank, ts)

        sorted_matches = sorted(candidates, key=sort_key, reverse=True)

        log_event(
            "signals.emails_ranked",
            total_evaluated=len(emails),
            matched_count=len(sorted_matches),
            critical_count=sum(1 for m in sorted_matches if m.priority == "Critical"),
            high_count=sum(1 for m in sorted_matches if m.priority == "High"),
        )

        return [(m.email, m.priority) for m in sorted_matches[:limit]]

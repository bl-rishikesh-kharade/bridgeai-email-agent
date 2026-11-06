import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import settings
from app.core.logger import log_event
from app.schemas.ai_analysis import AIAnalysis
from app.services.email_signals import EmailSignalEngine


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ListEmailsArgs(_Args):
    limit: int = Field(default=10, ge=1, le=20)


class SearchEmailsArgs(_Args):
    query: str = Field(min_length=1, max_length=200)
    sender_only: bool = False
    unread_only: bool = False
    limit: int = Field(default=10, ge=1, le=50)


class EmailIdArgs(_Args):
    email_id: str | None = Field(default=None, min_length=1, max_length=256)


class FilterArgs(_Args):
    filter_id: Literal["important_unread"]
    limit: int = Field(default=500, ge=1, le=500)
    exclude_senders: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)


@dataclass
class ToolOutcome:
    data: dict[str, Any]
    emails: list[Any] = field(default_factory=list)
    reviews: list[dict[str, Any]] = field(default_factory=list)
    current_email_id: str | None = None
    clear_current_email: bool = False
    used_recent_window: bool = False


TOOL_DECLARATIONS = [
    {"name": "list_recent_emails", "description": "List recent emails from the user's mailbox.", "parameters_json_schema": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 50}}, "additionalProperties": False}},
    {"name": "search_emails", "description": "Find matching emails by topic, subject, sender, or date constraints. You can search for unread emails (set unread_only: true), date ranges using Gmail query syntax (e.g. after:2026/10/01 before:2026/11/01), or specific senders/topics.", "parameters_json_schema": {"type": "object", "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 200}, "sender_only": {"type": "boolean"}, "unread_only": {"type": "boolean"}, "limit": {"type": "integer", "minimum": 1, "maximum": 50}}, "required": ["query"], "additionalProperties": False}},
    {"name": "get_email", "description": "Retrieve one exact email by ID, or the selected/current email when email_id is omitted.", "parameters_json_schema": {"type": "object", "properties": {"email_id": {"type": "string", "maxLength": 256}}, "additionalProperties": False}},
    {"name": "review_email", "description": "Summarize and analyze one exact email, including priority and action items.", "parameters_json_schema": {"type": "object", "properties": {"email_id": {"type": "string", "maxLength": 256}}, "additionalProperties": False}},
    {"name": "filter_unread_emails", "description": "Find unread important emails from the user's mailbox using priority signals. You can supply exclude_senders to omit specific senders/domains (e.g. ['chitkara.edu.in']), and exclude_keywords to omit specific topics or words (e.g. ['circular', 'newsletter', 'fee']).", "parameters_json_schema": {"type": "object", "properties": {"filter_id": {"type": "string", "enum": ["important_unread"]}, "limit": {"type": "integer", "minimum": 1, "maximum": 500}, "exclude_senders": {"type": "array", "items": {"type": "string"}}, "exclude_keywords": {"type": "array", "items": {"type": "string"}}}, "required": ["filter_id"], "additionalProperties": False}},
]


class EmailAgentTools:
    def __init__(self, email_provider, *, analyzer, signal_engine: EmailSignalEngine | None = None):
        self.email_provider = email_provider
        self.analyzer = analyzer
        self.signal_engine = signal_engine or EmailSignalEngine(settings.signals_config_path)
        self._handlers: dict[str, tuple[type[_Args], Callable[..., ToolOutcome]]] = {
            "list_recent_emails": (ListEmailsArgs, self._list_emails),
            "search_emails": (SearchEmailsArgs, self._search_emails),
            "get_email": (EmailIdArgs, self._get_email),
            "review_email": (EmailIdArgs, self._review_email),
            "filter_unread_emails": (FilterArgs, self._filter_unread),
        }

    def execute(self, name: str, arguments: dict[str, Any], request_context: dict[str, Any]) -> ToolOutcome:
        spec = self._handlers.get(name)
        if spec is None:
            return ToolOutcome({"error": "This operation is not available."})
        schema, handler = spec
        try:
            parsed = schema.model_validate(arguments or {})
            log_event("agent.tool.started", tool_name=name)
            outcome = handler(parsed, request_context)
            log_event("agent.tool.completed", tool_name=name, result_count=len(outcome.emails))
            return outcome
        except ValidationError:
            log_event("agent.tool.rejected", level=logging.WARNING, tool_name=name, reason="invalid_arguments")
            return ToolOutcome({"error": "The requested operation had invalid arguments. Please clarify the request."})
        except Exception as exc:
            root_cause = exc
            for _ in range(6):
                nested = root_cause.__cause__ or root_cause.__context__
                if nested is None:
                    break
                root_cause = nested
            response = getattr(root_cause, "resp", None)
            log_event(
                "agent.tool.failed", level=logging.ERROR, tool_name=name,
                error_type=type(exc).__name__,
                cause_type=type(root_cause).__name__ if root_cause is not exc else None,
                status_code=getattr(response, "status", None),
                api_status=getattr(root_cause, "status", None),
                winerror=getattr(root_cause, "winerror", None),
                errno=getattr(root_cause, "errno", None),
            )
            return ToolOutcome({"error": "The requested operation is temporarily unavailable. Please try again."})

    def _resolve_provider(self, request_context: dict[str, Any]):
        return request_context.get("email_provider") or self.email_provider

    def _resolve_email_id(self, args: EmailIdArgs, request_context: dict[str, Any]) -> str | None:
        return args.email_id or request_context.get("selected_email_id") or request_context.get("current_email_id")

    def _list_emails(self, args: ListEmailsArgs, request_context: dict[str, Any]) -> ToolOutcome:
        provider = self._resolve_provider(request_context)
        raw = provider.list_emails(min(args.limit, settings.max_email_list_limit))
        ranked = self.signal_engine.filter_and_rank_emails(raw, only_important=False, limit=args.limit)
        emails = [item[0] for item in ranked]
        reviews = [{"email_id": item[0].id, "priority": item[1]} for item in ranked]
        return ToolOutcome(
            {"count": len(emails), "emails": [self._email_brief(email) for email in emails]},
            emails=emails,
            reviews=reviews,
            current_email_id=emails[0].id if emails else None,
            clear_current_email=not emails,
        )

    def _search_emails(self, args: SearchEmailsArgs, request_context: dict[str, Any]) -> ToolOutcome:
        provider = self._resolve_provider(request_context)
        raw = provider.search_emails(args.query, limit=args.limit, sender_only=args.sender_only)
        if args.unread_only:
            raw = [e for e in raw if not e.is_read]
        ranked = self.signal_engine.filter_and_rank_emails(raw, only_important=False, limit=args.limit)
        emails = [item[0] for item in ranked]
        reviews = [{"email_id": item[0].id, "priority": item[1]} for item in ranked]
        return ToolOutcome(
            {"query": args.query, "unread_only": args.unread_only, "count": len(emails), "emails": [self._email_brief(email) for email in emails]},
            emails=emails,
            reviews=reviews,
            current_email_id=emails[0].id if emails else None,
            clear_current_email=not emails,
        )

    def _get_email(self, args: EmailIdArgs, request_context: dict[str, Any]) -> ToolOutcome:
        provider = self._resolve_provider(request_context)
        email_id = self._resolve_email_id(args, request_context)
        if not email_id:
            return ToolOutcome({"error": "Select an email or specify its exact email ID first."})
        email = provider.get_email(email_id)
        if email is None:
            return ToolOutcome({"error": "That exact email was not found or is inaccessible. No other email was substituted."},
                               clear_current_email=True)
        return ToolOutcome({"email": {**self._email_brief(email), "body": email.body[:settings.max_email_body_chars]},
                            "gmail_url": provider.gmail_url(email)},
                           emails=[email], current_email_id=email.id)

    def _review_email(self, args: EmailIdArgs, request_context: dict[str, Any]) -> ToolOutcome:
        retrieved = self._get_email(args, request_context)
        if "email" not in retrieved.data:
            return retrieved
        email = retrieved.emails[0]
        analysis = self.analyzer(email.subject, email.body)
        review = self._analysis_dict(email.id, analysis)
        return ToolOutcome({"review": review}, emails=[email], reviews=[review], current_email_id=email.id)

    def _filter_unread(self, args: FilterArgs, request_context: dict[str, Any]) -> ToolOutcome:
        strategy = getattr(settings, "importance_strategy", "signals")
        provider = self._resolve_provider(request_context)
        # Display limit defaults to 50 if not specified
        display_limit = min(args.limit, 50) if args.limit else 50

        if strategy == "signals":
            # 1. Candidate Pool: Always fetch a 100-email unread pool directly from Gmail
            # (No 48-hour cut-off, ensuring older unread critical/high emails are never missed)
            pool_limit = 100
            try:
                unread_pool = provider.list_filtered_emails("unread", limit=pool_limit)
            except Exception:
                unread_pool = provider.list_emails(limit=pool_limit)

            # 2. Priority Engine: Filter by signals, respecting sender and keyword exclusions, and sort strictly by priority
            # (Critical > High > Medium > Low, with newest timestamp within each tier)
            ranked = self.signal_engine.filter_and_rank_emails(
                unread_pool,
                only_important=True,
                limit=display_limit,
                exclude_senders=args.exclude_senders,
                exclude_keywords=args.exclude_keywords,
            )
            emails = [item[0] for item in ranked]
            reviews = [{"email_id": item[0].id, "priority": item[1]} for item in ranked]
            return ToolOutcome(
                {
                    "filter": args.filter_id,
                    "count": len(emails),
                    "strategy": "signals",
                    "pool_size": len(unread_pool),
                    "exclude_senders": args.exclude_senders,
                    "exclude_keywords": args.exclude_keywords,
                    "used_recent_window": False,
                },
                emails=emails,
                reviews=reviews,
                current_email_id=emails[0].id if emails else None,
                clear_current_email=not emails,
                used_recent_window=False,
            )

        # Strategy == "gmail" (Gmail native label:IMPORTANT)
        gmail_emails = provider.list_filtered_emails("important_unread", limit=display_limit)
        ranked_gmail = self.signal_engine.filter_and_rank_emails(
            gmail_emails,
            only_important=False,
            limit=display_limit,
            exclude_senders=args.exclude_senders,
            exclude_keywords=args.exclude_keywords,
        )
        emails = [item[0] for item in ranked_gmail]
        reviews = [{"email_id": item[0].id, "priority": item[1]} for item in ranked_gmail]
        return ToolOutcome(
            {
                "filter": args.filter_id,
                "count": len(emails),
                "strategy": "gmail",
                "used_recent_window": False,
            },
            emails=emails,
            reviews=reviews,
            current_email_id=emails[0].id if emails else None,
            clear_current_email=not emails,
            used_recent_window=False,
        )

    @staticmethod
    def _email_brief(email: Any) -> dict[str, Any]:
        return {"id": email.id, "sender": str(email.sender), "subject": email.subject,
                "received_at": email.received_at.isoformat() if email.received_at else None,
                "is_read": email.is_read}

    @staticmethod
    def _analysis_dict(email_id: str, result: AIAnalysis) -> dict[str, Any]:
        return {"email_id": email_id, "summary": result.summary, "priority": result.priority,
                "requires_action": result.requires_action, "requires_attention": result.requires_attention,
                "action_items": result.action_items}

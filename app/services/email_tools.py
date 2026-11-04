import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import settings
from app.core.logger import log_event
from app.schemas.ai_analysis import AIAnalysis


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ListEmailsArgs(_Args):
    limit: int = Field(default=10, ge=1, le=20)


class SearchEmailsArgs(_Args):
    query: str = Field(min_length=1, max_length=200)
    sender_only: bool = False
    limit: int = Field(default=10, ge=1, le=20)


class EmailIdArgs(_Args):
    email_id: str | None = Field(default=None, min_length=1, max_length=256)


class FilterArgs(_Args):
    filter_id: Literal["important_unread"]
    limit: int = Field(default=500, ge=1, le=500)


@dataclass
class ToolOutcome:
    data: dict[str, Any]
    emails: list[Any] = field(default_factory=list)
    reviews: list[dict[str, Any]] = field(default_factory=list)
    current_email_id: str | None = None
    clear_current_email: bool = False
    used_recent_window: bool = False


TOOL_DECLARATIONS = [
    {"name": "list_recent_emails", "description": "List recent emails from the user's mailbox.", "parameters_json_schema": {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 20}}, "additionalProperties": False}},
    {"name": "search_emails", "description": "Find matching emails. Set sender_only true only when looking for who sent an email; otherwise search subject and message content.", "parameters_json_schema": {"type": "object", "properties": {"query": {"type": "string", "minLength": 1, "maxLength": 200}, "sender_only": {"type": "boolean"}, "limit": {"type": "integer", "minimum": 1, "maximum": 20}}, "required": ["query"], "additionalProperties": False}},
    {"name": "get_email", "description": "Retrieve one exact email by ID, or the selected/current email when email_id is omitted.", "parameters_json_schema": {"type": "object", "properties": {"email_id": {"type": "string", "maxLength": 256}}, "additionalProperties": False}},
    {"name": "review_email", "description": "Summarize and analyze one exact email, including priority and action items.", "parameters_json_schema": {"type": "object", "properties": {"email_id": {"type": "string", "maxLength": 256}}, "additionalProperties": False}},
    {"name": "filter_unread_emails", "description": "Find emails Gmail marks as both unread and important. Use Gmail's UNREAD and IMPORTANT labels; do not infer importance from message text. If more than 100 emails match, limit results to important unread emails from the last 48 hours.", "parameters_json_schema": {"type": "object", "properties": {"filter_id": {"type": "string", "enum": ["important_unread"]}, "limit": {"type": "integer", "minimum": 1, "maximum": 500}}, "required": ["filter_id"], "additionalProperties": False}},
]


class EmailAgentTools:
    def __init__(self, email_provider, *, analyzer):
        self.email_provider = email_provider
        self.analyzer = analyzer
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

    def _resolve_email_id(self, args: EmailIdArgs, request_context: dict[str, Any]) -> str | None:
        return args.email_id or request_context.get("selected_email_id") or request_context.get("current_email_id")

    def _list_emails(self, args: ListEmailsArgs, _request_context: dict[str, Any]) -> ToolOutcome:
        emails = self.email_provider.list_emails(min(args.limit, settings.max_email_list_limit))
        return ToolOutcome({"count": len(emails), "emails": [self._email_brief(email) for email in emails]},
                           emails=emails, current_email_id=emails[0].id if emails else None,
                           clear_current_email=not emails)

    def _search_emails(self, args: SearchEmailsArgs, _request_context: dict[str, Any]) -> ToolOutcome:
        emails = self.email_provider.search_emails(args.query, limit=args.limit, sender_only=args.sender_only)
        return ToolOutcome({"query": args.query, "count": len(emails), "emails": [self._email_brief(email) for email in emails]},
                           emails=emails, current_email_id=emails[0].id if emails else None,
                           clear_current_email=not emails)

    def _get_email(self, args: EmailIdArgs, request_context: dict[str, Any]) -> ToolOutcome:
        email_id = self._resolve_email_id(args, request_context)
        if not email_id:
            return ToolOutcome({"error": "Select an email or specify its exact email ID first."})
        email = self.email_provider.get_email(email_id)
        if email is None:
            return ToolOutcome({"error": "That exact email was not found or is inaccessible. No other email was substituted."},
                               clear_current_email=True)
        return ToolOutcome({"email": {**self._email_brief(email), "body": email.body[:settings.max_email_body_chars]},
                            "gmail_url": self.email_provider.gmail_url(email)},
                           emails=[email], current_email_id=email.id)

    def _review_email(self, args: EmailIdArgs, request_context: dict[str, Any]) -> ToolOutcome:
        retrieved = self._get_email(args, request_context)
        if "email" not in retrieved.data:
            return retrieved
        email = retrieved.emails[0]
        analysis = self.analyzer(email.subject, email.body)
        review = self._analysis_dict(email.id, analysis)
        return ToolOutcome({"review": review}, emails=[email], reviews=[review], current_email_id=email.id)

    def _filter_unread(self, args: FilterArgs, _request_context: dict[str, Any]) -> ToolOutcome:
        count_unread = getattr(self.email_provider, "has_more_filtered_emails", None)
        use_recent_window = bool(count_unread("important_unread", threshold=100)) if count_unread else False
        query_filter = "important_unread_last_48_hours" if use_recent_window else "important_unread"
        emails = self.email_provider.list_filtered_emails(query_filter, limit=args.limit)
        return ToolOutcome(
            {"filter": args.filter_id, "count": len(emails), "used_recent_window": use_recent_window},
            emails=emails,
            current_email_id=emails[0].id if emails else None,
            clear_current_email=not emails,
            used_recent_window=use_recent_window,
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

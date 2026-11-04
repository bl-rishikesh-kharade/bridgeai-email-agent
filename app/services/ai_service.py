import logging
from dataclasses import dataclass
from time import perf_counter

from google import genai
from google.genai import types
from app.core.config import settings
from app.core.logger import log_event
from app.schemas.ai_analysis import AIAnalysis
from app.prompts.analyze_email_prompt import build_analyze_email_prompt


@dataclass(frozen=True)
class AgentToolCall:
    name: str
    arguments: dict


@dataclass(frozen=True)
class AgentTurn:
    text: str
    tool_calls: list[AgentToolCall]
    model_content: object


class AIServiceConfigurationError(RuntimeError):
    """Raised when AI analysis is requested without required configuration."""


class AIService:
    def __init__(self, api_key: str | None = None):
        if not api_key and not settings.gemini_api_key:
            raise AIServiceConfigurationError("Set GEMINI_API_KEY in the local environment to use email analysis.")
        self.client = genai.Client(
            api_key=api_key or settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=int(settings.gemini_timeout * 1000)),
        )

    def _generate_content(self, operation: str, prompt, config=None):
        started = perf_counter()
        log_event("model.request.started", operation=operation, model=settings.gemini_model)
        try:
            response = self.client.models.generate_content(
                model=settings.gemini_model, contents=prompt, config=config,
            )
        except Exception as exc:
            log_event(
                "model.request.failed", level=logging.ERROR, operation=operation,
                model=settings.gemini_model, error_type=type(exc).__name__,
                status_code=getattr(exc, "code", None), api_status=getattr(exc, "status", None),
                duration_ms=round((perf_counter() - started) * 1000, 2),
            )
            raise
        log_event(
            "model.request.completed", operation=operation,
            model=settings.gemini_model,
            duration_ms=round((perf_counter() - started) * 1000, 2),
        )
        return response

    def analyze_email(self, subject: str, body: str) -> AIAnalysis:
        body = body[:settings.max_email_body_chars]
        prompt = build_analyze_email_prompt(subject, body)
        response = self._generate_content(
            "email_analysis", prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": AIAnalysis,
            },
        )
        return AIAnalysis.model_validate_json(response.text)

    def agent_turn(self, messages, tool_declarations: list[dict], system_instruction: str, *, tools_enabled: bool = True) -> AgentTurn:
        """Ask Gemini to answer or request one of the application's declared tools."""
        tools = None
        if tools_enabled:
            declarations = [types.FunctionDeclaration(**item) for item in tool_declarations]
            tools = [types.Tool(function_declarations=declarations)]
        config = types.GenerateContentConfig(
            temperature=settings.gemini_temperature,
            system_instruction=system_instruction,
            tools=tools,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        response = self._generate_content("agent_turn", messages, config)
        candidates = getattr(response, "candidates", None) or []
        model_content = getattr(candidates[0], "content", None) if candidates else None
        calls = []
        for call in (getattr(response, "function_calls", None) or []):
            name = getattr(call, "name", None)
            args = getattr(call, "args", None)
            if isinstance(name, str) and isinstance(args, dict):
                calls.append(AgentToolCall(name=name, arguments=args))
        if calls and model_content is None:
            raise ValueError("Gemini returned tool calls without a model message.")
        return AgentTurn(text=(getattr(response, "text", None) or "").strip(),
                         tool_calls=calls, model_content=model_content)

_default_service: AIService | None = None


def get_ai_service() -> AIService:
    global _default_service
    if _default_service is None:
        _default_service = AIService()
    return _default_service


def analyze_email(subject: str, body: str) -> AIAnalysis:
    return get_ai_service().analyze_email(subject, body)


def agent_turn(messages, tool_declarations: list[dict], system_instruction: str, *, tools_enabled: bool = True) -> AgentTurn:
    return get_ai_service().agent_turn(messages, tool_declarations, system_instruction, tools_enabled=tools_enabled)


\n
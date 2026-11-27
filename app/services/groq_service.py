"""Groq AI Service implementing OpenAI-compatible fast inference and tool calling.

Provides sub-second response times (~300-500ms) with proactive, human-like reasoning
specifically designed for responsive conversation and future voice interaction.
"""

from dataclasses import dataclass
import json
import logging
from time import perf_counter
try:
    from groq import Groq
    HAS_GROQ = True
except ImportError:
    Groq = None
    HAS_GROQ = False

from app.core.config import settings
from app.core.logger import log_event, logger
from app.services.ai_service import AgentToolCall, AgentTurn, AIServiceConfigurationError


class GroqService:
    """Manages Groq chat completions, function calling, and fallback orchestration."""

    def __init__(self, api_key: str | None = None):
        if not HAS_GROQ or Groq is None:
            raise AIServiceConfigurationError("The 'groq' package is not installed.")
        self.api_key = api_key or settings.groq_api_key
        if not self.api_key:
            raise AIServiceConfigurationError("GROQ_API_KEY is not configured.")
        self.client = Groq(api_key=self.api_key)
        self.model = settings.groq_model or "qwen/qwen3.8-27b"

    def _convert_tool_declarations(self, tool_declarations: list[dict]) -> list[dict]:
        """Convert standard JSON schemas into OpenAI/Groq function calling format."""
        openai_tools = []
        for tool in tool_declarations:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters_json_schema", {}),
                },
            })
        return openai_tools

    def _convert_messages(self, messages: Any, system_instruction: str) -> list[dict]:
        """Convert multi-turn messages into standard OpenAI message format."""
        formatted_messages = [{"role": "system", "content": system_instruction}]

        for item in messages:
            # Handle Google genai types.Content objects if passed directly
            if hasattr(item, "role") and hasattr(item, "parts"):
                role = "assistant" if item.role == "model" else "user"
                content_parts = []
                for p in item.parts:
                    if hasattr(p, "text") and p.text:
                        content_parts.append(p.text)
                    elif hasattr(p, "function_response"):
                        # Function tool outcome
                        fn_name = getattr(p.function_response, "name", "tool")
                        resp_data = getattr(p.function_response, "response", {})
                        content_parts.append(f"Tool {fn_name} returned: {json.dumps(resp_data, default=str)}")
                formatted_messages.append({"role": role, "content": "\n".join(content_parts)})
            elif isinstance(item, dict):
                formatted_messages.append(item)

        return formatted_messages

    def agent_turn(
        self,
        messages: Any,
        tool_declarations: list[dict],
        system_instruction: str,
        *,
        tools_enabled: bool = True,
    ) -> AgentTurn:
        """Execute one conversational agent turn with Groq's high-speed inference."""
        started = perf_counter()
        log_event("groq.request.started", model=self.model)

        groq_messages = self._convert_messages(messages, system_instruction)
        tools = self._convert_tool_declarations(tool_declarations) if tools_enabled else None

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": groq_messages,
            "temperature": settings.gemini_temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            res = self.client.chat.completions.create(**kwargs)
            duration_ms = round((perf_counter() - started) * 1000, 2)
            log_event("groq.request.completed", model=self.model, duration_ms=duration_ms)

            choice = res.choices[0]
            choice_msg = choice.message
            content = (choice_msg.content or "").strip()

            tool_calls: list[AgentToolCall] = []
            if choice_msg.tool_calls:
                for tc in choice_msg.tool_calls:
                    fn_name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments) if isinstance(tc.function.arguments, str) else tc.function.arguments
                    except Exception:
                        args = {}
                    tool_calls.append(AgentToolCall(name=fn_name, arguments=args))

            return AgentTurn(
                text=content,
                tool_calls=tool_calls,
                model_content={"role": "assistant", "content": content or "Executed tool calls."},
            )
        except Exception as exc:
            duration_ms = round((perf_counter() - started) * 1000, 2)
            log_event(
                "groq.request.failed",
                model=self.model,
                duration_ms=duration_ms,
                error_type=type(exc).__name__,
                reason=str(exc),
            )
            raise


_default_groq_service: GroqService | None = None


def get_groq_service() -> GroqService:
    global _default_groq_service
    if _default_groq_service is None:
        _default_groq_service = GroqService()
    return _default_groq_service

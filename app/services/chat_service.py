"""Coordinate one chat request with direct Gemini SDK calls and Python tools."""

import logging
from functools import wraps
from time import perf_counter
from typing import Any

from google.genai import types

from app.core.logger import log_event, logger
from app.prompts.agent_system_prompt import build_agent_system_prompt
from app.services.ai_service import (
    AIServiceConfigurationError,
    AgentToolCall,
    agent_turn,
    analyze_email,
)
from app.services.email_tools import EmailAgentTools, TOOL_DECLARATIONS


MAX_TOOL_CALLS = 5
# The workspace shortcut runs its fixed Gmail operation without a Gemini call.
QUICK_ACTION_TOOL_CALLS = {
    "important_unread": ("filter_unread_emails", {"filter_id": "important_unread"}),
}


def _observe_step(name, step):
    @wraps(step)
    def observed(request_context: dict[str, Any]):
        started = perf_counter()
        log_event("chat.step.started", step=name)
        try:
            result = step(request_context)
        except Exception as exc:
            log_event("chat.step.failed", level=logging.ERROR, step=name,
                      duration_ms=round((perf_counter() - started) * 1000, 2),
                      error_type=type(exc).__name__)
            raise
        log_event("chat.step.completed", step=name,
                  result_count=len(result.get("email_results", [])),
                  duration_ms=round((perf_counter() - started) * 1000, 2))
        return result
    return observed


class ChatService:
    """Handle one request with direct Gemini calls and ordinary Python functions."""

    def __init__(
        self,
        email_provider,
        *,
        analyzer=analyze_email,
        model_turn=agent_turn,
        max_tool_calls: int = MAX_TOOL_CALLS,
    ):
        self.toolset = EmailAgentTools(
            email_provider,
            analyzer=analyzer,
        )
        self.model_turn = model_turn
        self.max_tool_calls = max_tool_calls

    def handle_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Process one message; the temporary request context is discarded afterward."""
        request_context = _observe_step("prepare_request", self._prepare_request)(dict(request))
        preset_calls = request_context.get("tool_calls", [])
        if preset_calls:
            request_context.update(_observe_step("run_tools", self._run_tools)(request_context))
            if not request_context.get("response") and request_context.get("filter_id") == "important_unread":
                count = len(request_context.get("email_results", []))
                if count:
                    response = f"Found {count} unread important email(s)."
                elif request_context.get("used_recent_window"):
                    response = "No unread important emails were found in the last 48 hours."
                else:
                    response = "No unread important emails were found."
                request_context["response"] = response

        while not request_context.get("response"):
            request_context.update(_observe_step("ask_gemini", self._ask_gemini)(request_context))
            if request_context.get("response") or not request_context.get("tool_calls"):
                break
            request_context.update(_observe_step("run_tools", self._run_tools)(request_context))

        request_context.pop("tool_calls", None)
        request_context.pop("messages", None)
        return request_context

    @staticmethod
    def _prepare_request(request_context: dict[str, Any]) -> dict[str, Any]:
        message = request_context.get("message", "")
        history = request_context.get("history", [])
        messages = []
        for turn in history:
            role = "model" if turn.get("role") == "assistant" else "user"
            text = (turn.get("text") or "").strip()
            if text:
                messages.append(types.Content(role=role, parts=[types.Part.from_text(text=text)]))
        messages.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))
        preset = QUICK_ACTION_TOOL_CALLS.get(request_context.get("filter_id"))
        calls = [AgentToolCall(name=preset[0], arguments=preset[1])] if preset else []
        return {
            **request_context,
            "messages": messages,
            "tool_calls": calls,
            "tool_call_count": 0,
            "email_results": [],
            "email_reviews": [],
        }

    def _ask_gemini(self, request_context: dict[str, Any]) -> dict[str, Any]:
        enabled = request_context.get("tool_call_count", 0) < self.max_tool_calls
        instruction = build_agent_system_prompt(
            current_email_id=request_context.get("current_email_id"),
            selected_email_id=request_context.get("selected_email_id"),
        )
        try:
            turn = self.model_turn(
                request_context.get("messages", []), TOOL_DECLARATIONS, instruction,
                tools_enabled=enabled,
            )
        except AIServiceConfigurationError:
            return {"response": "Chat needs Gemini. Set GEMINI_API_KEY and try again.", "tool_calls": []}
        except Exception as exc:
            logger.warning(
                "Gemini chat request failed (error_type=%s, status_code=%s, api_status=%s)",
                type(exc).__name__, getattr(exc, "code", None), getattr(exc, "status", None),
            )
            return {"response": "I couldn't complete that request right now. Please try again.", "tool_calls": []}

        messages = list(request_context.get("messages", []))
        if turn.model_content is not None:
            messages.append(turn.model_content)
        if turn.tool_calls:
            if not enabled:
                return {
                    "messages": messages,
                    "response": "I reached the safe limit for this request. Please try a smaller or more specific request.",
                    "tool_calls": [],
                }
            return {"messages": messages, "tool_calls": turn.tool_calls, "response": ""}
        return {
            "messages": messages,
            "response": turn.text or "I couldn't find a useful answer for that request. Could you rephrase it?",
            "tool_calls": [],
        }

    def _run_tools(self, request_context: dict[str, Any]) -> dict[str, Any]:
        calls = request_context.get("tool_calls", [])
        if not calls:
            return {"response": "I couldn't complete that request safely."}
        messages = list(request_context.get("messages", []))
        results = list(request_context.get("email_results", []))
        reviews = list(request_context.get("email_reviews", []))
        current_id = request_context.get("current_email_id")
        clear_current = False
        used_recent_window = False
        count = request_context.get("tool_call_count", 0)

        for call in calls:
            if count >= self.max_tool_calls:
                return {
                    "messages": messages,
                    "tool_calls": [],
                    "response": "I reached the safe limit for this request. Please try a smaller or more specific request.",
                    "email_results": results,
                    "email_reviews": reviews,
                    "current_email_id": current_id,
                }
            outcome = self.toolset.execute(call.name, call.arguments, request_context)
            if "error" in outcome.data:
                return {
                    "messages": messages,
                    "tool_calls": [],
                    "response": "I couldn't access Gmail to complete that request. Check your Google connection and try again.",
                    "email_results": results,
                    "email_reviews": reviews,
                    "current_email_id": current_id,
                    "used_recent_window": used_recent_window,
                }
            count += 1
            used_recent_window = used_recent_window or outcome.used_recent_window
            messages.append(types.Content(role="user", parts=[types.Part.from_function_response(
                name=call.name, response=outcome.data,
            )]))
            if outcome.emails or outcome.clear_current_email:
                results = outcome.emails
                reviews = outcome.reviews
                current_id = outcome.current_email_id
                clear_current = outcome.clear_current_email
            elif outcome.reviews:
                reviews = outcome.reviews
            if outcome.current_email_id:
                current_id = outcome.current_email_id
                clear_current = False

        return {
            "messages": messages,
            "tool_calls": [],
            "tool_call_count": count,
            "email_results": results,
            "email_reviews": reviews,
            "current_email_id": current_id,
            "clear_current_email": clear_current,
            "used_recent_window": used_recent_window,
        }


def build_chat_service(email_provider, **options) -> ChatService:
    """Wire the providers and direct Gemini call into the chat coordinator."""
    return ChatService(email_provider, **options)

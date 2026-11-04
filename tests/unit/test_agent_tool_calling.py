from google.genai import types

from app.services import ai_service


class FakeModels:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def test_agent_turn_uses_manual_function_calling_and_normalizes_tool_calls(monkeypatch):
    function_call = types.FunctionCall(name="search_emails", args={"query": "Karthik", "sender_only": True})
    content = types.Content(role="model", parts=[types.Part.from_function_call(name="search_emails", args={"query": "Karthik", "sender_only": True})])
    response = type("Response", (), {"text": None, "function_calls": [function_call],
                                     "candidates": [types.Candidate(content=content)]})()
    models = FakeModels(response)
    monkeypatch.setattr(ai_service.genai, "Client", lambda **_kwargs: type("Client", (), {"models": models})())
    service = ai_service.AIService(api_key="test-only")

    turn = service.agent_turn(
        [types.Content(role="user", parts=[types.Part.from_text(text="Did Karthik email me?")])],
        [{"name": "search_emails", "description": "Search email", "parameters_json_schema": {"type": "object", "properties": {"query": {"type": "string"}}}}],
        "Use the tools safely.",
    )

    assert turn.tool_calls[0].name == "search_emails"
    assert turn.tool_calls[0].arguments["sender_only"] is True
    config = models.calls[0]["config"]
    assert config.automatic_function_calling.disable is True
    assert config.system_instruction == "Use the tools safely."
    assert config.tools[0].function_declarations[0].name == "search_emails"


def test_agent_turn_can_disable_tools_after_workflow_limit(monkeypatch):
    content = types.Content(role="model", parts=[types.Part.from_text(text="Please narrow the request.")])
    response = type("Response", (), {"text": "Please narrow the request.", "function_calls": None,
                                     "candidates": [types.Candidate(content=content)]})()
    models = FakeModels(response)
    monkeypatch.setattr(ai_service.genai, "Client", lambda **_kwargs: type("Client", (), {"models": models})())
    service = ai_service.AIService(api_key="test-only")

    turn = service.agent_turn([], [{"name": "tool", "description": "test", "parameters_json_schema": {"type": "object"}}], "prompt", tools_enabled=False)

    assert turn.text == "Please narrow the request."
    assert models.calls[0]["config"].tools is None

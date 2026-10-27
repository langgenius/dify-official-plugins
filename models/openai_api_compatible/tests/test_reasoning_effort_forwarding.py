"""Unit tests for reasoning_effort forwarding in _invoke.

reasoning_effort is a standard OpenAI Chat Completions parameter. It must reach
the outgoing request whenever the user sets it, regardless of the thinking-mode
toggle (which only governs the non-standard vLLM/SGLang-style parameters).
"""

from unittest.mock import patch

from dify_plugin.entities.model.llm import LLMResult, LLMUsage
from dify_plugin.entities.model.message import AssistantPromptMessage, UserPromptMessage

from models.llm.llm import OpenAILargeLanguageModel

BASE_CREDENTIALS = {
    "endpoint_url": "https://api.example.com/v1/",
    "api_key": "test-key",
    "mode": "chat",
    "agent_thought_support": "supported",
    "compatibility_mode": "strict",
}

BASE_INVOKE = "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel._invoke"


def _captured_parameters(credentials, model_parameters):
    """Run _invoke with the SDK-level invoke stubbed and capture the forwarded parameters."""
    llm = OpenAILargeLanguageModel(model_schemas=[])
    usage = LLMUsage.empty_usage()
    stub_result = LLMResult(model="gpt-5.6-luna", prompt_messages=[], message=AssistantPromptMessage(content="ok"), usage=usage)
    with patch(BASE_INVOKE, return_value=stub_result) as base_invoke:
        llm._invoke(
            model="gpt-5.6-luna",
            credentials=credentials,
            prompt_messages=[UserPromptMessage(content="hi")],
            model_parameters=model_parameters,
            stream=False,
        )
    assert base_invoke.called
    return base_invoke.call_args.args[3]


def test_reasoning_effort_forwarded_with_thinking_toggle_off():
    params = _captured_parameters(BASE_CREDENTIALS, {"reasoning_effort": "high"})
    assert params.get("reasoning_effort") == "high"
    assert "chat_template_kwargs" not in params
    assert "thinking" not in params
    assert "enable_thinking" not in params


def test_reasoning_effort_forwarded_with_thinking_toggle_on():
    params = _captured_parameters(BASE_CREDENTIALS, {"reasoning_effort": "low", "enable_thinking": True})
    assert params.get("reasoning_effort") == "low"
    # Strict compatibility mode suppresses the non-standard template kwargs.
    assert "chat_template_kwargs" not in params


def test_reasoning_effort_template_kwargs_only_with_thinking_in_extended_mode():
    credentials = {**BASE_CREDENTIALS, "compatibility_mode": "extended"}
    params = _captured_parameters(credentials, {"reasoning_effort": "high", "enable_thinking": True})
    assert params.get("reasoning_effort") == "high"
    assert params.get("chat_template_kwargs", {}).get("reasoning_effort") == "high"


def test_reasoning_effort_absent_when_unset():
    params = _captured_parameters(BASE_CREDENTIALS, {})
    assert "reasoning_effort" not in params

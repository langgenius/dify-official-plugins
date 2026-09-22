from unittest.mock import MagicMock, patch

from dify_plugin.entities.model.message import (
    SystemPromptMessage,
    UserPromptMessage,
)

from models.llm.llm import OpenAILargeLanguageModel


def _prompt_messages():
    return [
        SystemPromptMessage(content="You are a helpful assistant."),
        UserPromptMessage(content="Hello"),
    ]


def _invoke_and_capture(model_parameters, credentials):
    model = OpenAILargeLanguageModel(model_schemas=[])
    captured = {}

    def fake_super(self, model, credentials, prompt_messages, model_parameters, tools, stop, stream, user):
        captured["model_parameters"] = dict(model_parameters)
        return MagicMock()

    with patch(
        "dify_plugin.interfaces.model.openai_compatible.llm.OAICompatLargeLanguageModel._invoke",
        new=fake_super,
    ):
        model._invoke(
            model="gpt-5",
            credentials=credentials,
            prompt_messages=_prompt_messages(),
            model_parameters=dict(model_parameters),
            stream=False,
        )

    return captured["model_parameters"]


def test_reasoning_effort_forwarded_when_thinking_toggle_off():
    params = _invoke_and_capture(
        {"reasoning_effort": "high"},
        {
            "mode": "chat",
            "agent_thought_support": "supported",
            "compatibility_mode": "strict",
        },
    )

    assert params.get("reasoning_effort") == "high"
    assert "chat_template_kwargs" not in params


def test_reasoning_effort_forwarded_when_thinking_toggle_on():
    params = _invoke_and_capture(
        {"reasoning_effort": "high", "enable_thinking": True},
        {
            "mode": "chat",
            "agent_thought_support": "supported",
            "compatibility_mode": "strict",
        },
    )

    assert params.get("reasoning_effort") == "high"


def test_reasoning_effort_dropped_when_thinking_forced_off():
    params = _invoke_and_capture(
        {"reasoning_effort": "high"},
        {
            "mode": "chat",
            "agent_thought_support": "not_supported",
            "compatibility_mode": "strict",
        },
    )

    assert "reasoning_effort" not in params


def test_reasoning_effort_forwarded_when_thinking_forced_on():
    params = _invoke_and_capture(
        {"reasoning_effort": "medium"},
        {
            "mode": "chat",
            "agent_thought_support": "only_thinking_supported",
            "compatibility_mode": "strict",
        },
    )

    assert params.get("reasoning_effort") == "medium"


def test_reasoning_effort_mirrored_to_chat_template_kwargs_in_extended_mode():
    params = _invoke_and_capture(
        {"reasoning_effort": "high", "enable_thinking": True},
        {
            "mode": "chat",
            "agent_thought_support": "supported",
            "compatibility_mode": "extended",
        },
    )

    assert params.get("reasoning_effort") == "high"
    assert params.get("chat_template_kwargs", {}).get("reasoning_effort") == "high"


def test_reasoning_effort_top_level_only_in_extended_mode_without_thinking_toggle():
    params = _invoke_and_capture(
        {"reasoning_effort": "high"},
        {
            "mode": "chat",
            "agent_thought_support": "supported",
            "compatibility_mode": "extended",
        },
    )

    assert params.get("reasoning_effort") == "high"
    assert "chat_template_kwargs" not in params

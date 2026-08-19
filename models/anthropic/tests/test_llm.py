from unittest.mock import patch

import pytest
from anthropic.types import Message, ThinkingBlock, ToolUseBlock, Usage
from dify_plugin.entities.model.message import (
    SystemPromptMessage,
    TextPromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.errors.model import CredentialsValidateFailedError

from models.llm.llm import AnthropicLargeLanguageModel, PromptCachingHandler


def test_get_cache_control_defaults_overrides_and_copies() -> None:
    assert PromptCachingHandler([]).get_cache_control() == {"type": "ephemeral"}

    expected = {"type": "ephemeral", "ttl": "1h"}
    handler = PromptCachingHandler([], cache_control=expected)
    actual = handler.get_cache_control()
    assert actual == expected

    actual["ttl"] = "5m"
    assert handler.get_cache_control() == {"type": "ephemeral", "ttl": "1h"}


def test_get_system_prompt_flattens_text() -> None:
    assert PromptCachingHandler([]).get_system_prompt() == ""

    messages = [
        UserPromptMessage(content="ignored"),
        SystemPromptMessage(content=" first <cache>literal</cache> "),
        SystemPromptMessage(
            content=[
                TextPromptMessageContent(data=" second "),
                TextPromptMessageContent(data=" third "),
            ]
        ),
    ]
    assert (
        PromptCachingHandler(messages).get_system_prompt()
        == "first <cache>literal</cache>\nsecond\nthird"
    )


def test_get_system_prompt_marks_cache_blocks() -> None:
    cache_control = {"type": "ephemeral", "ttl": "1h"}
    prompt = "prefix <cache>first\nline</cache> middle <cache>second</cache> suffix"
    handler = PromptCachingHandler(
        [SystemPromptMessage(content=prompt)],
        enable_system_cache=True,
        cache_control=cache_control,
    )
    assert handler.get_system_prompt() == [
        {"type": "text", "text": "prefix "},
        {"type": "text", "text": "first\nline", "cache_control": cache_control},
        {"type": "text", "text": " middle "},
        {"type": "text", "text": "second", "cache_control": cache_control},
        {"type": "text", "text": " suffix"},
    ]


def test_calc_adjusted_prompt_tokens() -> None:
    calculate = PromptCachingHandler.calc_adjusted_prompt_tokens

    assert calculate(1000) == 1000
    assert (
        calculate(
            1000,
            cache_creation_input_tokens=200,
            cache_creation_fallback_multiplier=2.0,
        )
        == 1400
    )
    assert (
        calculate(
            1000,
            cache_creation_input_tokens=107,
            cache_read_input_tokens=109,
            cache_creation_5m_input_tokens=101,
            cache_creation_1h_input_tokens=103,
            cache_creation_fallback_multiplier=2.0,
        )
        == 1342
    )


def test_validate_credentials_probes_and_wraps_error() -> None:
    model = AnthropicLargeLanguageModel()
    credentials = {"anthropic_api_key": "sk-test"}

    with patch.object(model, "_chat_generate") as generate:
        model.validate_credentials("claude-sonnet-4-6", credentials)

        generate.assert_called_once_with(
            model="claude-sonnet-4-6",
            credentials=credentials,
            prompt_messages=[UserPromptMessage(content="ping")],
            model_parameters={"temperature": 0, "max_tokens": 20},
            stream=False,
        )

        generate.side_effect = Exception("boom")
        with pytest.raises(CredentialsValidateFailedError, match="boom"):
            model.validate_credentials("claude-sonnet-4-6", credentials)


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("CLAUDE-SONNET-5", (True, False, True, False, False)),
        ("CLAUDE-OPUS-4-7-latest", (True, False, False, True, False)),
        ("CLAUDE-OPUS-4-8-latest", (True, False, False, True, False)),
        ("CLAUDE-FABLE-5-latest", (True, True, False, True, False)),
        ("CLAUDE-MYTHOS-5-latest", (True, True, False, True, False)),
        ("CLAUDE-OPUS-5-latest", (True, False, True, True, True)),
        ("CLAUDE-SONNET-4-6", (False, False, False, False, False)),
        ("not-claude-opus-5-latest", (False, False, False, False, False)),
    ],
)
def test_model_classification(model: str, expected: tuple[bool, ...]) -> None:
    llm = AnthropicLargeLanguageModel()
    assert (
        llm._uses_adaptive_thinking(model),
        llm._has_always_on_adaptive_thinking(model),
        llm._has_adaptive_thinking_default_on(model),
        llm._supports_task_budget(model),
        llm._enforces_disabled_thinking_effort_cap(model),
    ) == expected


def test_thinking_blocks_survive_a_fresh_model_instance() -> None:
    # dify_plugin.core.model_factory.ModelFactory.get_instance() builds a new model
    # instance per RPC ("generate stateless model instances"), so state kept on
    # self does not survive from the turn that produced a thinking block to the
    # turn that must echo it back on a tool-result continuation.
    response = Message(
        id="msg_1",
        model="claude-sonnet-5",
        role="assistant",
        stop_reason="tool_use",
        type="message",
        usage=Usage(input_tokens=10, output_tokens=5),
        content=[
            ThinkingBlock(
                type="thinking", thinking="working out the weather query", signature="sig-1"
            ),
            ToolUseBlock(type="tool_use", id="toolu_1", name="get_weather", input={"city": "Paris"}),
        ],
    )
    user_message = UserPromptMessage(content="what is the weather in Paris?")

    responding_instance = AnthropicLargeLanguageModel()
    assistant_message = responding_instance._handle_chat_generate_response(
        model="claude-sonnet-5",
        credentials={},
        response=response,
        prompt_messages=[user_message],
    ).message

    all_messages = [
        user_message,
        assistant_message,
        ToolPromptMessage(content="18C, sunny", tool_call_id="toolu_1"),
    ]

    # A separate instance, exactly as ModelFactory.get_instance() would build for
    # the follow-up RPC that sends the tool result back to Anthropic.
    followup_instance = AnthropicLargeLanguageModel()
    processed = followup_instance._process_assistant_message(assistant_message, all_messages)

    block_types = [block["type"] for block in processed["content"]]
    assert "thinking" in block_types

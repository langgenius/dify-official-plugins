"""Tests for native structured output (output_config.format) handling.

The previous permissive mock (``create(**kwargs)``) could not detect that the
real ``messages.create()`` rejects unknown keyword arguments — which is how the
unconsumed ``json_schema`` parameter caused a TypeError crash in JSON mode with
a user-defined schema. These tests use a signature-compatible mock that mirrors
the real SDK boundary.
"""

import inspect
import json

import pytest
from anthropic.resources.messages.messages import Messages as _SdkMessages
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    SystemPromptMessage,
    UserPromptMessage,
)
from models.llm import llm as llm_module
from models.llm.llm import AnthropicLargeLanguageModel

SCHEMA = (
    '{"type": "object", "properties": {"answer": {"type": "string"}}, '
    '"required": ["answer"]}'
)
PARSED_SCHEMA = json.loads(SCHEMA)


class _SignatureCheckedMessages:
    """Mimics the real SDK: rejects unknown keyword arguments like messages.create()."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._valid_params = set(inspect.signature(_SdkMessages.create).parameters)

    def create(self, **kwargs):
        unknown = set(kwargs) - self._valid_params
        if unknown:
            raise TypeError(
                f"create() got an unexpected keyword argument {min(unknown)!r}"
            )
        self.calls.append(kwargs)
        return object()


class _Anthropic:
    instances: list["_Anthropic"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.messages = _SignatureCheckedMessages()
        self.instances.append(self)


def _capture_payload(
    monkeypatch,
    model_parameters: dict,
    model: str = "claude-opus-5",
) -> dict:
    _Anthropic.instances = []
    monkeypatch.setattr(llm_module, "Anthropic", _Anthropic)

    AnthropicLargeLanguageModel()._chat_generate(
        model=model,
        credentials={"anthropic_api_key": "test-key"},
        prompt_messages=[UserPromptMessage(content="Hello")],
        model_parameters=dict(model_parameters),
        stream=True,
    )

    return _Anthropic.instances[0].messages.calls[0]


def test_json_schema_uses_native_structured_output(monkeypatch) -> None:
    payload = _capture_payload(
        monkeypatch,
        {"max_tokens": 1024, "json_schema": SCHEMA},
    )

    # The schema must not leak as an unknown kwarg (mock raises TypeError on that).
    assert "json_schema" not in payload
    assert payload["output_config"] == {
        "format": {"type": "json_schema", "schema": PARSED_SCHEMA}
    }


def test_json_schema_merges_with_adaptive_effort(monkeypatch) -> None:
    payload = _capture_payload(
        monkeypatch,
        {
            "max_tokens": 1024,
            "thinking": True,
            "thinking_display": "summarized",
            "effort": "max",
            "json_schema": SCHEMA,
        },
    )

    assert payload["output_config"] == {
        "effort": "max",
        "format": {"type": "json_schema", "schema": PARSED_SCHEMA},
    }
    assert payload["thinking"] == {"type": "adaptive", "display": "summarized"}


def test_json_schema_empty_string_is_ignored(monkeypatch) -> None:
    payload = _capture_payload(
        monkeypatch,
        {"max_tokens": 1024, "json_schema": "   "},
    )

    assert "output_config" not in payload
    assert "json_schema" not in payload


def test_json_schema_invalid_json_raises() -> None:
    with pytest.raises(ValueError, match="Invalid json_schema"):
        AnthropicLargeLanguageModel._parse_json_schema("{not json")


def test_json_schema_non_object_raises() -> None:
    with pytest.raises(ValueError, match="non-empty JSON object"):
        AnthropicLargeLanguageModel._parse_json_schema('["answer"]')


def test_json_schema_dict_passthrough() -> None:
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    assert AnthropicLargeLanguageModel._parse_json_schema(schema) == schema
    assert AnthropicLargeLanguageModel._parse_json_schema(None) is None
    assert AnthropicLargeLanguageModel._parse_json_schema("") is None


@pytest.mark.parametrize(
    "raw",
    ["null", "false", "0", "[]", "{}"],
)
def test_parse_json_schema_rejects_non_objects(raw: str) -> None:
    with pytest.raises(ValueError, match="non-empty JSON object"):
        AnthropicLargeLanguageModel._parse_json_schema(raw)


@pytest.mark.parametrize("raw", [0, 1.5, ["a"], (1,)])
def test_parse_json_schema_rejects_unsupported_types(raw: object) -> None:
    with pytest.raises(ValueError, match="Unsupported json_schema type"):
        AnthropicLargeLanguageModel._parse_json_schema(raw)


def _capture_invoke(monkeypatch, model_parameters: dict, model: str = "claude-sonnet-4-5"):
    llm = AnthropicLargeLanguageModel()
    captured: dict = {}

    def fake_invoke(
        model, credentials, prompt_messages, model_parameters,
        tools=None, stop=None, stream=True, user=None,
    ):
        captured["model_parameters"] = dict(model_parameters)
        captured["prompt_messages"] = list(prompt_messages)
        return iter(())

    monkeypatch.setattr(llm, "_invoke", fake_invoke)
    return llm, captured


def test_wrapper_skips_fence_hack_with_json_schema(monkeypatch) -> None:
    llm, captured = _capture_invoke(monkeypatch, {})
    prompt_messages = [
        SystemPromptMessage(content="original system"),
        UserPromptMessage(content="hi"),
    ]

    llm._code_block_mode_wrapper(
        model="claude-sonnet-4-5",
        credentials={"anthropic_api_key": "test-key"},
        prompt_messages=prompt_messages,
        model_parameters={
            "max_tokens": 1024,
            "response_format": "JSON",
            "json_schema": SCHEMA,
        },
        stream=True,
    )

    # Native path: prompts untouched, response_format consumed, json_schema kept
    # for _chat_generate to send via output_config.format.
    assert captured["model_parameters"]["json_schema"] == SCHEMA
    assert "response_format" not in captured["model_parameters"]
    assert isinstance(prompt_messages[0], SystemPromptMessage)
    assert prompt_messages[0].content == "original system"
    assert len(prompt_messages) == 2


def test_wrapper_keeps_fence_hack_without_schema(monkeypatch) -> None:
    llm, captured = _capture_invoke(monkeypatch, {})
    prompt_messages = [
        SystemPromptMessage(content="original system"),
        UserPromptMessage(content="hi"),
    ]

    llm._code_block_mode_wrapper(
        model="claude-sonnet-4-5",
        credentials={"anthropic_api_key": "test-key"},
        prompt_messages=prompt_messages,
        model_parameters={
            "max_tokens": 1024,
            "response_format": "JSON",
        },
        stream=True,
    )

    # Legacy path: system prompt rewritten, assistant prefill appended.
    assert "response_format" not in captured["model_parameters"]
    assert "json_schema" not in captured["model_parameters"]
    assert "output a valid JSON object" in str(prompt_messages[0].content)
    assert "original system" in str(prompt_messages[0].content)
    assert isinstance(prompt_messages[-1], AssistantPromptMessage)
    assert "```JSON" in str(prompt_messages[-1].content)


def test_wrapper_falsy_non_string_schema_not_dropped(monkeypatch) -> None:
    # An empty dict is a *provided* (invalid) schema: the wrapper must keep it so
    # _chat_generate / _parse_json_schema can raise, not silently fall back to
    # the legacy fence hack.
    llm, captured = _capture_invoke(monkeypatch, {})
    prompt_messages = [
        SystemPromptMessage(content="original system"),
        UserPromptMessage(content="hi"),
    ]

    llm._code_block_mode_wrapper(
        model="claude-sonnet-4-5",
        credentials={"anthropic_api_key": "test-key"},
        prompt_messages=prompt_messages,
        model_parameters={
            "max_tokens": 1024,
            "response_format": "JSON",
            "json_schema": {},
        },
        stream=True,
    )

    assert captured["model_parameters"]["json_schema"] == {}
    assert "response_format" not in captured["model_parameters"]
    assert prompt_messages[0].content == "original system"
    assert len(prompt_messages) == 2


def test_wrapper_xml_mode_drops_json_schema(monkeypatch) -> None:
    llm, captured = _capture_invoke(monkeypatch, {})
    prompt_messages = [
        SystemPromptMessage(content="original system"),
        UserPromptMessage(content="hi"),
    ]

    llm._code_block_mode_wrapper(
        model="claude-sonnet-4-5",
        credentials={"anthropic_api_key": "test-key"},
        prompt_messages=prompt_messages,
        model_parameters={
            "max_tokens": 1024,
            "response_format": "XML",
            "json_schema": SCHEMA,
        },
        stream=True,
    )

    # XML keeps the fence hack; json_schema must not reach the API call.
    assert "json_schema" not in captured["model_parameters"]
    assert "response_format" not in captured["model_parameters"]
    assert "output a valid XML object" in str(prompt_messages[0].content)

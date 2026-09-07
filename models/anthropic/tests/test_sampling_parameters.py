"""Regression tests for Anthropic SDK 1.x sampling-parameter compatibility."""

import inspect

import pytest
from anthropic.resources.messages.messages import Messages as _SdkMessages
from dify_plugin.entities.model.message import PromptMessageTool, UserPromptMessage

from models.llm import llm as llm_module
from models.llm.llm import AnthropicLargeLanguageModel


class _SignatureCheckedMessages:
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
        return _Response()


class _Response:
    def model_dump_json(self, **kwargs) -> str:
        return "{}"


class _Anthropic:
    instances: list["_Anthropic"] = []

    def __init__(self, **kwargs) -> None:
        self.messages = _SignatureCheckedMessages()
        self.instances.append(self)


def _capture_payload(
    monkeypatch,
    model_parameters: dict,
    *,
    stream: bool = True,
    tools: list[PromptMessageTool] | None = None,
) -> dict:
    _Anthropic.instances = []
    monkeypatch.setattr(llm_module, "Anthropic", _Anthropic)

    llm = AnthropicLargeLanguageModel()
    if not stream:
        monkeypatch.setattr(llm, "_handle_chat_generate_response", lambda *args: object())

    llm._chat_generate(
        model="claude-sonnet-4-6",
        credentials={"anthropic_api_key": "test-key"},
        prompt_messages=[UserPromptMessage(content="Hello")],
        model_parameters=dict(model_parameters),
        tools=tools,
        stream=stream,
    )

    return _Anthropic.instances[0].messages.calls[0]


@pytest.mark.parametrize("stream", [True, False])
def test_sampling_parameters_use_extra_body_with_sdk_1_x(monkeypatch, stream) -> None:
    payload = _capture_payload(
        monkeypatch,
        {
            "max_tokens": 1024,
            "temperature": 0.7,
            "top_p": 0,
            "top_k": 40,
        },
        stream=stream,
    )

    assert not {"temperature", "top_p", "top_k"} & payload.keys()
    assert payload["extra_body"] == {
        "temperature": 0.7,
        "top_p": 0,
        "top_k": 40,
    }


def test_sampling_parameters_merge_with_existing_extra_body(monkeypatch) -> None:
    payload = _capture_payload(
        monkeypatch,
        {
            "max_tokens": 1024,
            "temperature": 0.7,
            "extra_body": {"custom_parameter": True, "temperature": 0.1},
        },
    )

    assert payload["extra_body"] == {
        "custom_parameter": True,
        "temperature": 0.7,
    }


def test_sampling_parameters_use_extra_body_with_tools(monkeypatch) -> None:
    tool = PromptMessageTool(
        name="lookup",
        description="Look something up",
        parameters={"type": "object", "properties": {}},
    )

    payload = _capture_payload(
        monkeypatch,
        {"max_tokens": 1024, "temperature": 0.7},
        tools=[tool],
    )

    assert payload["extra_body"] == {"temperature": 0.7}
    assert payload["tools"] == [
        {
            "name": "lookup",
            "description": "Look something up",
            "input_schema": {"type": "object", "properties": {}},
        }
    ]


def test_thinking_removes_sampling_parameters(monkeypatch) -> None:
    payload = _capture_payload(
        monkeypatch,
        {
            "max_tokens": 4096,
            "thinking": True,
            "thinking_budget": 1024,
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": 40,
        },
    )

    assert payload["thinking"] == {"type": "enabled", "budget_tokens": 1024}
    assert "extra_body" not in payload

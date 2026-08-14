import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
import yaml
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessageTool,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.errors.model import CredentialsValidateFailedError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from models.llm.llm import DeepseekLargeLanguageModel
from provider.deepseek import DeepSeekProvider


def _llm() -> DeepseekLargeLanguageModel:
    return DeepseekLargeLanguageModel(model_schemas=[])


def test_v4_catalog_and_parameter_boundaries() -> None:
    directory = ROOT / "models" / "llm"
    position = yaml.safe_load((directory / "_position.yaml").read_text())

    assert position == ["deepseek-v4-flash", "deepseek-v4-pro"]
    assert {
        path.stem for path in directory.glob("*.yaml") if path.name != "_position.yaml"
    } == set(position)

    for model in position:
        schema = yaml.safe_load((directory / f"{model}.yaml").read_text())
        AIModelEntity.model_validate(schema)
        rules = {rule["name"]: rule for rule in schema["parameter_rules"]}
        assert schema["model_properties"]["context_size"] == 1_000_000
        assert rules["max_tokens"]["max"] == 384_000
        assert rules["thinking"]["default"] is True
        assert rules["reasoning_effort"]["default"] == "high"
        assert rules["reasoning_effort"]["options"] == ["low", "high", "max"]
        assert rules["response_format"]["options"] == ["text", "json_object"]
        assert "pricing" not in schema


@pytest.mark.parametrize("thinking", [True, False])
def test_thinking_parameters_are_normalized(thinking: bool) -> None:
    unsupported = {
        "temperature": 0.7,
        "top_p": 0.8,
        "presence_penalty": 0.1,
        "frequency_penalty": 0.2,
    }
    parameters = {
        "thinking": thinking,
        "reasoning_effort": "low",
        "max_tokens": 7,
        **unsupported,
    }

    _llm()._normalize_model_parameters("deepseek-v4-pro", parameters)

    expected = {
        "thinking": {"type": "enabled" if thinking else "disabled"},
        "max_tokens": 7,
    }
    if thinking:
        expected["reasoning_effort"] = "low"
    else:
        expected.update(unsupported)
    assert parameters == expected

    if thinking:
        implicit_parameters = {"temperature": 0.7, "top_p": 0.8}
        _llm()._normalize_model_parameters("deepseek-v4-pro", implicit_parameters)
        assert implicit_parameters == {"thinking": {"type": "enabled"}}


def test_sdk_stream_wrapper_keeps_reasoning_content_and_tools() -> None:
    reasoning_content = "  reason </think> & &lt;\n"
    output, is_reasoning = _llm()._wrap_thinking_by_reasoning_content(
        {"reasoning_content": reasoning_content, "content": "answer"},
        False,
    )
    assert _llm()._extract_reasoning_content(output) == ("answer", reasoning_content)
    assert "<!--dify-deepseek-reasoning-->" in output
    assert is_reasoning is False

    opening, is_reasoning = _llm()._wrap_thinking_by_reasoning_content(
        {"reasoning_content": reasoning_content},
        False,
    )
    closing, is_reasoning = _llm()._wrap_thinking_by_reasoning_content(
        {"content": "answer"},
        is_reasoning,
    )
    assert _llm()._extract_reasoning_content(opening + closing) == (
        "answer",
        reasoning_content,
    )
    assert is_reasoning is False
    assert _llm()._extract_reasoning_content(opening + "\n</think>") == (
        "",
        reasoning_content,
    )

    output, is_reasoning = _llm()._wrap_thinking_by_reasoning_content(
        {"reasoning_content": reasoning_content, "tool_calls": [{}]},
        False,
    )
    assert _llm()._extract_reasoning_content(output) == ("", reasoning_content)
    assert is_reasoning is False


def test_non_stream_reasoning_and_tool_history_round_trip() -> None:
    reasoning_content = "  must preserve </think> & &lt; exactly\n"
    response = Mock()
    response.json.return_value = {
        "id": "chatcmpl-1",
        "model": "deepseek-v4-pro",
        "choices": [
            {
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": reasoning_content,
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "search", "arguments": "{}"},
                        }
                    ],
                },
            }
        ],
        "usage": {
            "prompt_tokens": 1,
            "completion_tokens": 2,
            "total_tokens": 3,
        },
    }
    credentials = {
        "mode": "chat",
        "function_calling_type": "tool_call",
    }
    llm = _llm()

    result = llm._handle_generate_response(
        "deepseek-v4-pro",
        credentials,
        response,
        [UserPromptMessage(content="hi")],
    )
    stored_message = AssistantPromptMessage(
        content=result.message.content,
        tool_calls=result.message.tool_calls,
    )

    for message in (result.message, stored_message):
        payload = llm._convert_prompt_message_to_dict(
            message,
            {
                "_current_model": "deepseek-v4-pro",
                "function_calling_type": "tool_call",
            },
        )
        assert payload["content"] == ""
        assert payload["reasoning_content"] == reasoning_content
        assert payload["tool_calls"][0]["id"] == "call_1"

    tool_payload = llm._convert_prompt_message_to_dict(
        ToolPromptMessage(content="result", tool_call_id="call_1"),
        {"function_calling_type": "tool_call"},
    )
    assert tool_payload == {
        "role": "tool",
        "content": "result",
        "tool_call_id": "call_1",
    }

    [merged] = llm._clean_messages(
        [
            AssistantPromptMessage(
                content=(
                    "<think>\n<!--dify-deepseek-reasoning-->r1\n</think>"
                    "a <think>literal answer tag</think>"
                ),
                opaque_body={"reasoning_content": "r1"},
            ),
            AssistantPromptMessage(
                content="<think>\n<!--dify-deepseek-reasoning-->r2\n</think>b",
                opaque_body={"reasoning_content": "r2"},
            ),
        ]
    )
    assert llm._convert_prompt_message_to_dict(
        merged,
        {"_current_model": "deepseek-v4-pro"},
    ) == {
        "role": "assistant",
        "content": "a <think>literal answer tag</think>\n\nb",
        "reasoning_content": "r1\n\nr2",
    }


def test_invoke_uses_official_user_id_and_default_endpoint() -> None:
    captured = {}

    def invoke(
        self,
        model,
        credentials,
        prompt_messages,
        model_parameters,
        tools=None,
        stop=None,
        stream=True,
        user=None,
    ):
        captured.update(
            model=model,
            credentials=credentials,
            parameters=model_parameters,
            tools=tools,
            user=user,
        )
        return "ok"

    credentials = {"api_key": "test", "endpoint_url": ""}
    with patch.object(OAICompatLargeLanguageModel, "_invoke", invoke):
        result = _llm()._invoke(
            "deepseek-v4-pro",
            credentials,
            [UserPromptMessage(content="hi")],
            {},
            tools=[
                PromptMessageTool(
                    name="search",
                    description="Search",
                    parameters={"type": "object", "properties": {}},
                )
            ],
            stream=False,
            user="user-1",
        )

    assert result == "ok"
    assert captured["model"] == "deepseek-v4-pro"
    assert captured["parameters"]["user_id"] == "user-1"
    assert captured["parameters"]["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "search",
                "description": "Search",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    assert "tool_choice" not in captured["parameters"]
    assert captured["tools"] is None
    assert captured["user"] is None
    assert credentials["_current_model"] == "deepseek-v4-pro"
    assert credentials["endpoint_url"] == "https://api.deepseek.com"


def test_provider_validation_does_not_fallback_to_retired_models() -> None:
    provider = object.__new__(DeepSeekProvider)
    model_instance = MagicMock()
    error = CredentialsValidateFailedError("model not exist")
    model_instance.validate_credentials.side_effect = error
    credentials = {"api_key": "test"}

    with (
        patch.object(
            DeepSeekProvider,
            "get_model_instance",
            return_value=model_instance,
        ),
        pytest.raises(CredentialsValidateFailedError) as raised,
    ):
        provider.validate_provider_credentials(credentials)

    assert raised.value is error
    model_instance.validate_credentials.assert_called_once_with(
        model="deepseek-v4-flash",
        credentials=credentials,
    )

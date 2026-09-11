import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
import yaml
from dify_plugin import OAICompatLargeLanguageModel
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    ImagePromptMessageContent,
    PromptMessageTool,
    TextPromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
)
from dify_plugin.errors.model import CredentialsValidateFailedError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from models.llm.llm import DeepseekLargeLanguageModel
from provider.deepseek import DeepSeekProvider

MODELS = (
    "deepseek-flash",
    "deepseek-v4-flash",
    "deepseek-v4-flash-vision-exp",
    "deepseek-v4-pro",
)


def _llm() -> DeepseekLargeLanguageModel:
    return DeepseekLargeLanguageModel(model_schemas=[])


def test_current_catalog_and_parameter_boundaries() -> None:
    directory = ROOT / "models" / "llm"
    position = yaml.safe_load((directory / "_position.yaml").read_text())

    assert position == list(MODELS)
    assert {
        path.stem for path in directory.glob("*.yaml") if path.name != "_position.yaml"
    } == set(position)

    for model in position:
        schema = yaml.safe_load((directory / f"{model}.yaml").read_text())
        entity = AIModelEntity.model_validate(schema)
        rules = {rule["name"]: rule for rule in schema["parameter_rules"]}
        assert ("vision" in schema["features"]) == (
            model in ("deepseek-flash", "deepseek-v4-flash-vision-exp")
        )
        assert schema["model_properties"]["context_size"] == 1_000_000
        maximum = 393_216 if model == "deepseek-flash" else 384_000
        assert rules["max_tokens"]["max"] == maximum
        assert rules["max_tokens"]["default"] == (
            65_536 if model == "deepseek-flash" else 4_096
        )
        assert rules["top_p"]["min"] == (0.95 if model == "deepseek-flash" else 0.01)
        assert rules["top_p"]["max"] == 1
        assert rules["thinking"]["default"] is True
        assert rules["reasoning_effort"]["default"] == "high"
        assert rules["reasoning_effort"]["options"] == ["low", "high", "max"]
        assert rules["response_format"]["options"] == ["text", "json_object"]
        assert "pricing" not in schema

        llm = DeepseekLargeLanguageModel(model_schemas=[entity])
        with patch.object(
            DeepseekLargeLanguageModel, "_invoke", return_value=iter(())
        ) as invoke:
            list(llm.invoke(model, {}, [], {"max_tokens": maximum}))
            assert invoke.call_args.args[3]["max_tokens"] == maximum
            with pytest.raises(ValueError, match=f"max_tokens.*{maximum}"):
                list(llm.invoke(model, {}, [], {"max_tokens": maximum + 1}))
            assert invoke.call_count == 1


@pytest.mark.parametrize(
    ("thinking", "enabled"),
    [
        pytest.param(None, True, id="default"),
        pytest.param(True, True, id="boolean-enabled"),
        pytest.param(False, False, id="boolean-disabled"),
        pytest.param({"type": "enabled"}, True, id="object-enabled"),
        pytest.param({"type": "disabled"}, False, id="object-disabled"),
    ],
)
@pytest.mark.parametrize("top_p", [0.95, 1.0])
@pytest.mark.parametrize("model", MODELS)
def test_thinking_parameters_are_normalized(
    model: str, thinking: bool | dict | None, enabled: bool, top_p: float
) -> None:
    unsupported = {
        "temperature": 0.7,
        "presence_penalty": 0.1,
        "frequency_penalty": 0.2,
    }
    parameters = {
        "reasoning_effort": "low",
        "max_tokens": 7,
        "top_p": top_p,
        **unsupported,
    }
    if thinking is not None:
        parameters["thinking"] = thinking

    _llm()._normalize_model_parameters(model, parameters)

    expected = {
        "thinking": {"type": "enabled" if enabled else "disabled"},
        "max_tokens": 7,
    }
    if enabled:
        expected["reasoning_effort"] = "low"
        if model == "deepseek-flash":
            expected["top_p"] = top_p
    else:
        expected.update(unsupported)
        if model != "deepseek-flash":
            expected["top_p"] = top_p
    assert parameters == expected


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


@pytest.mark.parametrize("model", MODELS)
def test_non_stream_reasoning_and_tool_history_round_trip(model: str) -> None:
    reasoning_content = "  must preserve </think> & &lt; exactly\n"
    response = Mock()
    response.json.return_value = {
        "id": "chatcmpl-1",
        "model": model,
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
        model,
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
                "_current_model": model,
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
        {"_current_model": model},
    ) == {
        "role": "assistant",
        "content": "a <think>literal answer tag</think>\n\nb",
        "reasoning_content": "r1\n\nr2",
    }


@pytest.mark.parametrize("model", MODELS)
def test_invoke_uses_official_user_id_and_default_endpoint(model: str) -> None:
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
            model,
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
    assert captured["model"] == model
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
    assert credentials["_current_model"] == model
    assert credentials["endpoint_url"] == "https://api.deepseek.com"


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("thinking", [False, True])
@pytest.mark.parametrize("model", ["deepseek-flash", "deepseek-v4-flash-vision-exp"])
def test_vision_images_reach_chat_completions(
    model: str, stream: bool, thinking: bool
) -> None:
    schema = AIModelEntity.model_validate(
        yaml.safe_load((ROOT / "models" / "llm" / f"{model}.yaml").read_text())
    )
    llm = DeepseekLargeLanguageModel(model_schemas=[schema])
    top_p = 0.95 if model == "deepseek-flash" else 0.8
    images = [
        ImagePromptMessageContent(
            format="png", mime_type="image/png", url="https://example.com/image.png"
        ),
        ImagePromptMessageContent(
            format="png",
            mime_type="image/png",
            base64_data="aW1hZ2U=",
            detail=ImagePromptMessageContent.DETAIL.HIGH,
        ),
    ]
    tool_call = {
        "id": "call_images",
        "type": "function",
        "function": {"name": "get_images", "arguments": "{}"},
    }
    messages = [
        UserPromptMessage(content="Compare these images."),
        UserPromptMessage(content=images),
        UserPromptMessage(content="Describe the difference."),
        AssistantPromptMessage(content="I can compare them."),
        UserPromptMessage(content="Please continue."),
        AssistantPromptMessage(
            content="",
            tool_calls=[AssistantPromptMessage.ToolCall.model_validate(tool_call)],
            opaque_body={"reasoning_content": "Need an image."},
        ),
        ToolPromptMessage(
            content=[TextPromptMessageContent(data="Captured images."), *images],
            tool_call_id="call_images",
        ),
    ]
    originals = [message.model_copy(deep=True) for message in messages]
    usage = {"prompt_tokens": 400, "completion_tokens": 2, "total_tokens": 402}
    response = Mock(status_code=200, encoding="utf-8")
    response.json.return_value = {
        "model": model,
        "choices": [
            {"message": {"content": "Different colors."}, "finish_reason": "stop"}
        ],
        "usage": usage,
    }
    response.iter_lines.return_value = [
        'data: {"choices":[{"delta":{"content":"Different colors."},"finish_reason":null}]}',
        "data: "
        + json.dumps(
            {
                "choices": [{"delta": {}, "finish_reason": "stop"}],
                "usage": usage,
            }
        ),
        "data: [DONE]",
    ]

    with patch("requests.post", return_value=response) as post:
        result = llm.invoke(
            model,
            {"api_key": "test"},
            messages,
            {
                "thinking": thinking,
                "reasoning_effort": "low",
                "top_p": top_p,
                "temperature": 0.7,
                "max_tokens": 4_096,
            },
            tools=[
                PromptMessageTool(
                    name="get_images",
                    description="Capture images.",
                    parameters={"type": "object", "properties": {}},
                )
            ],
            stream=stream,
        )
        result = list(result)[-1].delta

    assert result.usage.prompt_tokens == 400
    assert messages == originals
    assert post.call_args.args == ("https://api.deepseek.com/chat/completions",)
    payload = json.loads(post.call_args.kwargs["data"])
    assert payload["model"] == model
    assert payload["max_tokens"] == 4_096
    assert payload["stream"] is stream
    assert payload["thinking"] == {"type": "enabled" if thinking else "disabled"}
    if thinking:
        assert payload["reasoning_effort"] == "low"
        assert "temperature" not in payload
    else:
        assert "reasoning_effort" not in payload
        assert payload["temperature"] == 0.7
    if thinking == (model == "deepseek-flash"):
        assert payload["top_p"] == top_p
    else:
        assert "top_p" not in payload
    expected_images = [
        {
            "type": "image_url",
            "image_url": {"url": "https://example.com/image.png", "detail": "low"},
        },
        {
            "type": "image_url",
            "image_url": {"url": "data:image/png;base64,aW1hZ2U=", "detail": "high"},
        },
    ]
    assert payload["messages"] == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Compare these images."},
                *expected_images,
                {"type": "text", "text": "Describe the difference."},
            ],
        },
        {
            "role": "assistant",
            "content": "I can compare them.",
            "reasoning_content": "",
        },
        {"role": "user", "content": "Please continue."},
        {
            "role": "assistant",
            "content": "",
            "reasoning_content": "Need an image.",
            "tool_calls": [tool_call],
        },
        {
            "role": "tool",
            "content": [
                {"type": "text", "text": "Captured images."},
                *expected_images,
            ],
            "tool_call_id": "call_images",
        },
    ]


def test_provider_validation_keeps_existing_model_and_propagates_errors() -> None:
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

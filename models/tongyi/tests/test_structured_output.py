"""Exercise registered model parameters and the real DashScope HTTP serializer offline."""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest
from dify_plugin.config.config import DifyPluginEnv
from dify_plugin.core.plugin_registration import PluginRegistration
from dify_plugin.entities.model import ModelFeature, ModelType
from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    AudioPromptMessageContent,
    ImagePromptMessageContent,
    PromptMessageTool,
    SystemPromptMessage,
    TextPromptMessageContent,
    ToolPromptMessage,
    UserPromptMessage,
    VideoPromptMessageContent,
)
from dify_plugin.errors.model import InvokeBadRequestError
from requests import Response

SCHEMA_MODELS = (
    "deepseek-v4.1-flash",
    "deepseek-v4.1-flash-1017",
    "deepseek-v4-pro",
    "qwen3.7-max",
    "qwen3.7-plus",
    "qwen3.7-plus-2026-05-26",
    "qwen3.7-flash",
    "qwen3.7-flash-2026-07-15",
    "qwen3.8-max",
    "qwen3.8-flash",
)
CREDENTIALS = {"dashscope_api_key": "test-key", "api_host": "workspace.example.test"}
OUTPUT_SCHEMA = {
    "name": "llm_response",
    "schema": {
        "type": "object",
        "properties": {
            "answer": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "enum": ["ONLY_ALLOWED"]},
                    "ok": {"type": "boolean"},
                },
                "required": ["label", "ok"],
                "additionalProperties": False,
            },
            "items": {"type": "array", "items": {"type": "integer"}},
            "note": {"type": "string", "description": "可选备注"},
        },
        "required": ["answer", "items"],
        "additionalProperties": False,
    },
}
ANSWER = '{"answer":{"label":"ONLY_ALLOWED","ok":true},"items":[1,2]}'


@pytest.fixture(scope="module")
def model():
    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(Path(__file__).resolve().parents[1])
        registration = PluginRegistration(DifyPluginEnv())
    return registration.get_model_instance("tongyi", ModelType.LLM)


@pytest.fixture
def http_calls(monkeypatch):
    calls = []

    def post(session, url, **kwargs):
        body = json.loads(kwargs["data"])
        session.close = Mock(wraps=session.close)
        calls.append(
            {"url": url, "body": body, "stream": kwargs["stream"], "session": session}
        )
        vision = "multimodal-generation" in url

        def payload(content, finish_reason=None, reasoning=""):
            return {
                "request_id": "offline-request",
                "output": {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": [{"text": content}]
                                if vision and content
                                else content,
                                "reasoning_content": reasoning,
                            },
                            "finish_reason": finish_reason,
                        }
                    ]
                },
                "usage": {"input_tokens": 7, "output_tokens": 3},
            }

        response = Response()
        response.status_code = 200
        response.encoding = "utf-8"
        response._content_consumed = True
        if kwargs["stream"]:
            chunks = []
            if body["parameters"].get("enable_thinking"):
                chunks.append(payload("", reasoning="reasoning"))
            chunks.extend([payload(ANSWER), payload("", "stop")])
            response.headers["content-type"] = "text/event-stream"
            response._content = "".join(
                f"data: {json.dumps(chunk)}\n\n" for chunk in chunks
            ).encode()
        else:
            response.headers["content-type"] = "application/json"
            response._content = json.dumps(payload(ANSWER, "stop")).encode()
        return response

    monkeypatch.setattr("requests.Session.post", post)
    return calls


@pytest.mark.parametrize("name", SCHEMA_MODELS)
@pytest.mark.parametrize("thinking", [False, True])
@pytest.mark.parametrize("strict", [None, False, True])
def test_public_invoke_preserves_schema_thinking_output_and_usage(
    model, http_calls, name, thinking, strict
):
    schema = deepcopy(OUTPUT_SCHEMA)
    if strict is not None:
        schema["strict"] = strict
    parameters = {
        "response_format": "json_schema",
        "json_schema": json.dumps(schema),
        "enable_thinking": thinking,
    }
    original = deepcopy(parameters)
    messages = [UserPromptMessage(content=[TextPromptMessageContent(data="提取字段")])]

    chunks = list(model.invoke(name, CREDENTIALS, messages, parameters, stream=False))

    registered = model.get_model_schema(name, CREDENTIALS)
    assert ModelFeature.STRUCTURED_OUTPUT in registered.features
    call = http_calls[0]
    route = (
        "multimodal-generation"
        if ModelFeature.VISION in registered.features
        else "text-generation"
    )
    assert (
        call["url"]
        == f"https://workspace.example.test/api/v1/services/aigc/{route}/generation"
    )
    assert call["body"]["parameters"]["response_format"] == {
        "type": "json_schema",
        "json_schema": {**schema, "strict": True if strict is None else strict},
    }
    assert "json_schema" not in call["body"]["parameters"]
    assert call["body"]["input"]["messages"] == [
        {"role": "user", "content": [{"text": "提取字段"}]}
    ]
    assert call["stream"] is thinking
    content = "".join(chunk.delta.message.content for chunk in chunks)
    assert content == ("<think>\nreasoning\n</think>" if thinking else "") + ANSWER
    assert chunks[-1].delta.usage.prompt_tokens == 7
    assert chunks[-1].delta.usage.completion_tokens == 3
    assert parameters == original
    call["session"].close.assert_called_once()


@pytest.mark.parametrize(
    "media_type,format",
    [
        (ImagePromptMessageContent, "png"),
        (VideoPromptMessageContent, "mp4"),
        (AudioPromptMessageContent, "wav"),
    ],
)
@pytest.mark.parametrize("with_system", [False, True])
def test_media_uses_schema_prompt_and_preserves_messages(
    model, http_calls, media_type, format, with_system
):
    media = media_type(
        format=format,
        mime_type=f"{media_type.model_fields['type'].default}/{format}",
        url=f"https://example.test/input.{format}",
    )
    messages = [
        UserPromptMessage(
            content=[TextPromptMessageContent(data="Extract the fields."), media]
        ),
        AssistantPromptMessage(
            content="Checking.",
            tool_calls=[
                AssistantPromptMessage.ToolCall(
                    id="call_lookup",
                    type="function",
                    function={"name": "lookup", "arguments": "{}"},
                )
            ],
        ),
        ToolPromptMessage(content="Found.", tool_call_id="call_lookup"),
        UserPromptMessage(content="Use the earlier attachment."),
    ]
    if with_system:
        messages[:0] = [
            SystemPromptMessage(content="Keep this instruction."),
            SystemPromptMessage(content="Keep this too."),
        ]
    original = deepcopy(messages)
    expected = model._convert_prompt_messages_to_tongyi_messages(
        messages, rich_content=True
    )
    parameters = {
        "response_format": "json_schema",
        "json_schema": json.dumps(OUTPUT_SCHEMA),
        "enable_thinking": False,
    }
    tools = [
        PromptMessageTool(
            name="lookup",
            description="Look up fields",
            parameters={"type": "object", "properties": {}},
        )
    ]

    list(
        model.invoke(
            "qwen3.8-flash", CREDENTIALS, messages, parameters, tools=tools, stream=True
        )
    )

    body = http_calls[0]["body"]
    assert body["parameters"]["response_format"] == {"type": "json_object"}
    actual = body["input"]["messages"]
    schema_prompt = actual[0]["content"][0]["text"]
    assert (
        json.loads(schema_prompt.split("JSON Schema:\n", 1)[1])
        == OUTPUT_SCHEMA["schema"]
    )
    if with_system:
        assert schema_prompt.startswith("Keep this instruction.\n\n")
        assert actual[1:] == expected[1:]
    else:
        assert actual[1:] == expected
    assert actual[0]["role"] == "system"
    assert body["parameters"]["tools"] == model._convert_tools(tools)
    assert messages == original


@pytest.mark.parametrize(
    "name", ["deepseek-v4-flash-0731", "deepseek-v4.1-flash-1017", "qwen3.8-max"]
)
@pytest.mark.parametrize("response_format", [None, "text", "json_object"])
def test_plain_and_json_object_requests_keep_their_format(
    model, http_calls, name, response_format
):
    parameters = {"enable_thinking": False}
    if response_format:
        parameters["response_format"] = response_format
    list(
        model.invoke(
            name,
            CREDENTIALS,
            [UserPromptMessage(content="Return JSON.")],
            parameters,
            stream=False,
        )
    )
    sent = http_calls[0]["body"]["parameters"]
    assert sent.get("response_format") == (
        {"type": response_format} if response_format else None
    )
    if name == "deepseek-v4-flash-0731":
        assert (
            ModelFeature.STRUCTURED_OUTPUT
            not in model.get_model_schema(name, CREDENTIALS).features
        )


@pytest.mark.parametrize(
    "schema", [None, "{", "null", "[]", '"text"', '{"schema": []}']
)
def test_invalid_schema_fails_before_http(model, http_calls, schema):
    parameters = {"response_format": "json_schema"}
    if schema is not None:
        parameters["json_schema"] = schema
    with pytest.raises(InvokeBadRequestError, match="json_schema"):
        list(
            model.invoke(
                "deepseek-v4.1-flash-1017",
                CREDENTIALS,
                [],
                parameters,
            )
        )
    assert not http_calls


@pytest.mark.parametrize("strict", [None, False])
def test_generate_accepts_schema_dict_without_mutating_it(model, http_calls, strict):
    schema = deepcopy(OUTPUT_SCHEMA)
    if strict is not None:
        schema["strict"] = strict
    parameters = {
        "response_format": "json_schema",
        "json_schema": schema,
        "enable_thinking": False,
    }
    original = deepcopy(parameters)
    model._generate(
        "deepseek-v4.1-flash-1017",
        CREDENTIALS,
        [UserPromptMessage(content="Extract fields.")],
        parameters,
        stream=False,
    )
    assert parameters == original
    assert http_calls[0]["body"]["parameters"]["response_format"]["json_schema"][
        "strict"
    ] is (True if strict is None else strict)

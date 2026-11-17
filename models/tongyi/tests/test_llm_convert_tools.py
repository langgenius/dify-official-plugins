"""Keep tool schemas intact through public invocation and DashScope serialization."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from dify_plugin.config.config import DifyPluginEnv
from dify_plugin.core.plugin_registration import PluginRegistration
from dify_plugin.entities.model import ModelType
from dify_plugin.entities.model.message import PromptMessageTool, UserPromptMessage
from requests import Response


@pytest.fixture(scope="module")
def model():
    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(Path(__file__).resolve().parents[1])
        registration = PluginRegistration(DifyPluginEnv())
    return registration.get_model_instance("tongyi", ModelType.LLM)


@pytest.mark.parametrize("name", ["deepseek-v4-pro", "qwen3.8-flash"])
@pytest.mark.parametrize(
    "parameters",
    [
        {},
        {"type": "object"},
        {"type": "object", "properties": {"city": {"type": "string"}}},
        {
            "type": "object",
            "properties": {
                "city_or_id": {"anyOf": [{"type": "string"}, {"type": "integer"}]}
            },
            "required": ["city_or_id"],
        },
        {"type": "object", "properties": {"unit": {"enum": ["c", "f"]}}},
        {
            "type": "object",
            "properties": {"retries": {"type": ["integer", "string"], "enum": [1, 3, "auto"]}},
            "required": ["retries"],
        },
        {
            "type": "object",
            "$defs": {"sku": {"type": "string", "pattern": "^[A-Z]+$"}},
            "properties": {
                "order": {
                    "type": "object",
                    "properties": {
                        "sku": {"$ref": "#/$defs/sku"},
                        "quantity": {"type": "integer", "enum": [1, 3]},
                        "gift": {"type": "boolean"},
                    },
                    "required": ["sku", "quantity"],
                    "additionalProperties": False,
                },
                "labels": {
                    "type": "array",
                    "items": {"enum": ["new", "used"]},
                    "minItems": 1,
                },
            },
            "required": ["order"],
            "additionalProperties": False,
        },
    ],
    ids=["empty", "no-properties", "optional", "any-of", "enum-only", "mixed-enum", "nested"],
)
def test_public_invoke_preserves_tool_schema(model, monkeypatch, name, parameters):
    original = deepcopy(parameters)
    tool = PromptMessageTool(name="configure", description="Configure an order", parameters=parameters)
    requests = []

    def post(session, url, **kwargs):
        requests.append({"url": url, "body": json.loads(kwargs["data"])})
        assert kwargs["stream"] is False
        content = [{"text": "done"}] if "multimodal-generation" in url else "done"
        response = Response()
        response.status_code = 200
        response.encoding = "utf-8"
        response._content_consumed = True
        response.headers["content-type"] = "application/json"
        response._content = json.dumps(
            {
                "request_id": "offline-tool-schema",
                "output": {
                    "choices": [
                        {"message": {"role": "assistant", "content": content}, "finish_reason": "stop"}
                    ]
                },
                "usage": {"input_tokens": 3, "output_tokens": 1},
            }
        ).encode()
        return response

    monkeypatch.setattr("requests.Session.post", post)
    chunks = list(
        model.invoke(
            name,
            {"dashscope_api_key": "test-key"},
            [UserPromptMessage(content="Configure the order.")],
            {"enable_thinking": False},
            tools=[tool],
            stream=False,
        )
    )

    assert len(requests) == 1
    assert requests[0]["body"]["parameters"]["tools"] == [
        {
            "type": "function",
            "function": {
                "name": "configure",
                "description": "Configure an order",
                "parameters": original,
            },
        }
    ]
    assert "".join(chunk.delta.message.content for chunk in chunks) == "done"
    assert tool.parameters == original
    assert parameters == original

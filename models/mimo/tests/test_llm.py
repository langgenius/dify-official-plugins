"""Exercise the V2.6 catalog and HTTP payloads without calling Xiaomi."""

import json
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import (
    ImagePromptMessageContent,
    PromptMessageTool,
    SystemPromptMessage,
    TextPromptMessageContent,
    UserPromptMessage,
    VideoPromptMessageContent,
)
from dify_plugin.errors.model import CredentialsValidateFailedError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from models.llm.llm import MimoLargeLanguageModel
from provider.mimo import MimoProvider

MODELS = ("mimo-v2.6-pro", "mimo-v2.6-flash", "mimo-v2.6-pro-ultraspeed")


def make_llm():
    schemas = [
        AIModelEntity.model_validate(yaml.safe_load(path.read_text()))
        for path in (ROOT / "models/llm").glob("mimo-*.yaml")
    ]
    return MimoLargeLanguageModel(model_schemas=schemas)


def test_catalog_and_output_limit():
    llm = make_llm()
    assert {schema.model for schema in llm.model_schemas} == set(MODELS)
    assert yaml.safe_load((ROOT / "models/llm/_position.yaml").read_text()) == list(
        MODELS
    )
    for model in MODELS:
        with patch.object(
            MimoLargeLanguageModel, "_invoke", return_value=iter(())
        ) as invoke:
            list(llm.invoke(model, {}, [], {"max_completion_tokens": 131072}))
            assert invoke.call_args.args[3]["max_completion_tokens"] == 131072
            for invalid in (0, 131073):
                with pytest.raises(ValueError, match="max_completion_tokens"):
                    list(llm.invoke(model, {}, [], {"max_completion_tokens": invalid}))


@pytest.mark.parametrize(
    "endpoint",
    [
        None,
        "https://token-plan-cn.xiaomimimo.com/v1",
        "https://token-plan-sgp.xiaomimimo.com/v1",
        "https://token-plan-ams.xiaomimimo.com/v1",
    ],
)
@pytest.mark.parametrize("status", [200, 401])
def test_provider_validation_uses_v26_and_preserves_endpoint(endpoint, status):
    llm = make_llm()
    provider = MimoProvider(provider_schemas=Mock(), model_factory=Mock())
    credentials = {
        "api_key": "tp-test" if endpoint else "sk-test",
        "endpoint_url": endpoint,
        "enable_request_metadata": "enabled",
        "app_id": "test-app",
    }
    response = requests.Response()
    response.status_code = status
    response._content = b'{"object":"chat.completion","choices":[]}'
    with (
        patch.object(provider, "get_model_instance", return_value=llm),
        patch("requests.post", return_value=response) as post,
    ):
        if status == 200:
            provider.validate_provider_credentials(credentials)
        else:
            with pytest.raises(CredentialsValidateFailedError, match="401"):
                provider.validate_provider_credentials(credentials)

    assert (
        post.call_args.args[0]
        == (endpoint or "https://api.xiaomimimo.com/v1") + "/chat/completions"
    )
    body = post.call_args.kwargs["json"]
    assert body["model"] == "mimo-v2.6-flash"
    assert body["thinking"] == {"type": "disabled"}
    assert body["max_completion_tokens"] == 5
    assert "max_tokens" not in body
    assert post.call_args.kwargs["headers"]["X-Dify-App-Id"] == "test-app"
    assert (
        post.call_args.kwargs["headers"]["Authorization"]
        == f"Bearer {credentials['api_key']}"
    )


@pytest.mark.parametrize("model", MODELS)
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("thinking", ["disabled", "enabled"])
def test_v26_requests_and_responses(model, stream, thinking):
    llm = make_llm()
    tool_call = {
        "id": "call_1",
        "type": "function",
        "function": {"name": "lookup", "arguments": "{}"},
    }
    message = {"role": "assistant", "content": "", "tool_calls": [tool_call]}
    usage = {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}
    response = Mock(status_code=200, encoding="utf-8")
    response.json.return_value = {
        "id": "test-response",
        "model": model,
        "choices": [{"message": message, "finish_reason": "tool_calls"}],
        "usage": usage,
    }
    response.iter_lines.return_value = iter(
        [
            "data: "
            + json.dumps(
                {
                    "choices": [
                        {
                            "delta": {
                                "content": "",
                                "tool_calls": [{"index": 0, **tool_call}],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": usage,
                }
            ),
            "data: [DONE]",
        ]
    )
    prompts = [
        SystemPromptMessage(content="Return JSON."),
        UserPromptMessage(
            content=[
                TextPromptMessageContent(data="Describe these files."),
                ImagePromptMessageContent(
                    url="https://example.com/image.png",
                    format="png",
                    mime_type="image/png",
                ),
                VideoPromptMessageContent(
                    url="https://example.com/video.mp4",
                    format="mp4",
                    mime_type="video/mp4",
                ),
            ]
        ),
    ]
    with patch("requests.post", return_value=response) as post:
        result = llm.invoke(
            model=model,
            credentials={"api_key": "sk-test"},
            prompt_messages=prompts,
            model_parameters={
                "max_completion_tokens": 1024,
                "thinking": thinking,
                "response_format": "json_object",
            },
            tools=[
                PromptMessageTool(
                    name="lookup",
                    description="Look up information",
                    parameters={"type": "object", "properties": {}},
                )
            ],
            stream=stream,
        )
        chunks = list(result)
        assert any(
            call.function.name == "lookup"
            for chunk in chunks
            for call in chunk.delta.message.tool_calls
        )
        assert chunks[-1].delta.usage.total_tokens == 12

    body = json.loads(post.call_args.kwargs["data"])
    assert body["model"] == model
    assert body["stream"] is stream
    assert body["thinking"] == {"type": thinking}
    assert body["max_completion_tokens"] == 1024
    assert "max_tokens" not in body
    assert body["response_format"] == {"type": "json_object"}
    assert body["tools"][0]["function"]["name"] == "lookup"
    assert body["messages"][0] == {"role": "system", "content": "Return JSON."}
    assert [part["type"] for part in body["messages"][1]["content"]] == [
        "text",
        "image_url",
        "video_url",
    ]

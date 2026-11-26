import json
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
from dify_plugin import DifyPluginEnv
from dify_plugin.core.plugin_registration import PluginRegistration
from dify_plugin.entities.model import ModelType
from dify_plugin.entities.model.message import (
    ImagePromptMessageContent,
    SystemPromptMessage,
    TextPromptMessageContent,
    UserPromptMessage,
)
from dify_plugin.errors.model import CredentialsValidateFailedError, InvokeError
from tencentcloud.lkeap.v20240522.lkeap_client import LkeapClient


@pytest.fixture
def provider_and_llm():
    registration = PluginRegistration(DifyPluginEnv())
    _, provider, factory = registration.models_mapping["hunyuan"]
    return provider, factory.get_instance(ModelType.LLM)


def test_tokenhub_and_legacy_credentials_use_separate_apis(provider_and_llm):
    provider, _ = provider_and_llm
    credentials = {"tokenhub_api_key": "tokenhub-key", "secret_id": "id", "secret_key": "secret"}
    with patch("requests.get") as get, patch.object(LkeapClient, "GetEmbedding") as embed:
        provider.validate_provider_credentials(credentials)
        assert get.call_args.args[0] == "https://tokenhub.tencentmaas.com/v1/models"
        assert get.call_args.kwargs["headers"]["Authorization"] == "Bearer tokenhub-key"
        embed.assert_not_called()

        provider.validate_provider_credentials({"secret_id": "id", "secret_key": "secret"})
        request = embed.call_args.args[0]
        assert request.Model == "lke-text-embedding-v1"
        assert request.Inputs == ["hello"]

    with pytest.raises(CredentialsValidateFailedError, match="Enter both"):
        provider.validate_provider_credentials({"secret_id": "id"})


def test_tokenhub_chat_sends_thinking_and_stream_usage(provider_and_llm):
    _, llm = provider_and_llm
    with patch("requests.post") as post:
        post.return_value.status_code = 200
        llm._invoke(
            "hy4",
            {"tokenhub_api_key": "tokenhub-key"},
            [UserPromptMessage(content="Hello")],
            {"enable_thinking": False, "max_tokens": 2048},
        )
    assert post.call_args.args[0] == "https://tokenhub.tencentmaas.com/v1/chat/completions"
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer tokenhub-key"
    assert json.loads(post.call_args.kwargs["data"]) == {
        "model": "hy4",
        "messages": [{"role": "user", "content": "Hello"}],
        "stream": True,
        "max_tokens": 2048,
        "thinking": {"type": "disabled"},
        "stream_options": {"include_usage": True},
    }


def test_tokenhub_image_returns_dify_image_and_billed_usage(provider_and_llm):
    _, llm = provider_and_llm
    messages = [
        SystemPromptMessage(content="Use a watercolor style."),
        UserPromptMessage(
            content=[
                TextPromptMessageContent(data="Draw a cat."),
                ImagePromptMessageContent(format="png", mime_type="image/png", base64_data="aW1hZ2U="),
            ]
        ),
    ]
    image_url = "https://example.com/generated.png?signed=1"
    response = Mock()
    response.json.return_value = {
        "choices": [{"delta": {"type": "image", "image": {"url": image_url}}, "finish_reason": None}],
        "tokenhub_usage": {"total_tokens": 15000},
    }
    with patch("requests.post") as post:
        post.return_value.__enter__.return_value = response
        (chunk,) = llm.invoke(
            "hy-image-v3.5-preview", {"tokenhub_api_key": "key"}, messages, {"size": "2048x2048"}
        )

    assert post.call_args.args[0] == "https://tokenhub.tencentmaas.com/v1/wand/hunyuan-image/v35-generation"
    assert post.call_args.kwargs["json"] == {
        "model": "hy-image-v3.5-preview",
        "size": "2048x2048",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Use a watercolor style."},
                    {"type": "text", "text": "Draw a cat."},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,aW1hZ2U="}},
                ],
            }
        ],
    }
    (output,) = chunk.delta.message.content
    assert isinstance(output, ImagePromptMessageContent)
    assert output.url == image_url
    assert chunk.delta.usage.total_tokens == 15000
    assert chunk.delta.usage.total_price == Decimal("0.15")


def test_tokenhub_image_reports_upstream_error(provider_and_llm):
    _, llm = provider_and_llm
    with patch("requests.post") as post:
        post.return_value.__enter__.return_value.json.return_value = {
            "error": {"code": "content_filter", "message": "input moderation rejected"},
        }
        with pytest.raises(InvokeError, match="input moderation rejected"):
            list(
                llm.invoke(
                    "hy-image-v3.5-preview",
                    {"tokenhub_api_key": "key"},
                    [UserPromptMessage(content="Prompt")],
                )
            )

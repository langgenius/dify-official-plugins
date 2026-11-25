import json
from unittest.mock import patch

import pytest

from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    PromptMessageTool,
    UserPromptMessage,
)
from dify_plugin.errors.model import CredentialsValidateFailedError, InvokeError
from models.llm.llm import SarvamLargeLanguageModel, USER_AGENT


class FakeResponse:
    def __init__(
        self,
        payload: dict | None = None,
        status_code: int = 200,
        content_type: str = "application/json",
        chunks: list[bytes] | None = None,
    ) -> None:
        self._payload = payload or {}
        self.status_code = status_code
        self.encoding = "utf-8"
        self.headers = {"Content-Type": content_type}
        self.text = json.dumps(self._payload)
        self._chunks = chunks or []

    def json(self) -> dict:
        return self._payload

    def iter_content(self, chunk_size: int = 512):
        del chunk_size
        yield from self._chunks

    def iter_lines(self, decode_unicode: bool = False, delimiter: str = "\n\n"):
        del decode_unicode
        for chunk in self._chunks:
            text = chunk.decode("utf-8") if isinstance(chunk, bytes) else chunk
            for line in text.split(delimiter):
                if line:
                    yield line

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def chat_payload(content: str = "OK", reasoning: str | None = None) -> dict:
    message = {"role": "assistant", "content": content}
    if reasoning is not None:
        message["reasoning_content"] = reasoning
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "model": "sarvam-105b",
        "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4},
    }


def invoke(llm: SarvamLargeLanguageModel, **overrides):
    params = {
        "model": "sarvam-105b",
        "credentials": {"api_key": "test-key"},
        "prompt_messages": [UserPromptMessage(content="hi")],
        "model_parameters": {"max_tokens": 16},
        "stream": False,
    }
    params.update(overrides)
    return llm._invoke(**params)


def test_invoke_uses_v2_and_user_agent() -> None:
    llm = SarvamLargeLanguageModel(model_schemas=[])
    with patch("requests.post", return_value=FakeResponse(chat_payload())) as post:
        result = invoke(llm)

    args, kwargs = post.call_args
    assert args[0] == "https://api.sarvam.ai/v2/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert kwargs["headers"]["User-Agent"] == USER_AGENT
    body = json.loads(kwargs["data"])
    assert body["model"] == "sarvam-105b"
    assert body["max_tokens"] == 16
    assert body["stream"] is False
    assert result.message.content == "OK"


def test_invoke_respects_custom_endpoint() -> None:
    llm = SarvamLargeLanguageModel(model_schemas=[])
    with patch("requests.post", return_value=FakeResponse(chat_payload())) as post:
        invoke(llm, credentials={"api_key": "test-key", "endpoint_url": "https://example.test/v2"})

    args, _ = post.call_args
    assert args[0] == "https://example.test/v2/chat/completions"


def test_conversations_model_uses_v2() -> None:
    llm = SarvamLargeLanguageModel(model_schemas=[])
    with patch("requests.post", return_value=FakeResponse(chat_payload())) as post:
        invoke(llm, model="sarvam-105b-conversations")

    args, _ = post.call_args
    assert args[0] == "https://api.sarvam.ai/v2/chat/completions"


def test_extra_headers_are_preserved() -> None:
    llm = SarvamLargeLanguageModel(model_schemas=[])
    credentials = {"api_key": "test-key", "extra_headers": {"X-Test": "1"}}
    with patch("requests.post", return_value=FakeResponse(chat_payload())) as post:
        invoke(llm, credentials=credentials)

    _, kwargs = post.call_args
    assert kwargs["headers"]["X-Test"] == "1"
    assert kwargs["headers"]["User-Agent"] == USER_AGENT


def test_extra_headers_json_string_is_parsed() -> None:
    llm = SarvamLargeLanguageModel(model_schemas=[])
    credentials = {"api_key": "test-key", "extra_headers": '{"X-Test": "1"}'}
    with patch("requests.post", return_value=FakeResponse(chat_payload())) as post:
        invoke(llm, credentials=credentials)

    _, kwargs = post.call_args
    assert kwargs["headers"]["X-Test"] == "1"
    assert kwargs["headers"]["User-Agent"] == USER_AGENT


def test_validate_credentials_uses_user_agent_and_64_tokens() -> None:
    llm = SarvamLargeLanguageModel(model_schemas=[])
    payload = {"object": "chat.completion", "choices": [{"message": {"content": "OK"}}]}
    with patch("requests.post", return_value=FakeResponse(payload)) as post:
        llm.validate_credentials("sarvam-105b", {"api_key": "test-key"})

    args, kwargs = post.call_args
    assert args[0] == "https://api.sarvam.ai/v2/chat/completions"
    assert kwargs["headers"]["User-Agent"] == USER_AGENT
    assert kwargs["json"]["max_tokens"] == 64


def test_validate_credentials_403_raises() -> None:
    llm = SarvamLargeLanguageModel(model_schemas=[])
    with patch("requests.post", return_value=FakeResponse({"error": "bad key"}, status_code=403)):
        with pytest.raises(CredentialsValidateFailedError):
            llm.validate_credentials("sarvam-105b", {"api_key": "bad"})


def test_invoke_429_raises() -> None:
    llm = SarvamLargeLanguageModel(model_schemas=[])
    with patch("requests.post", return_value=FakeResponse({"error": "rate"}, status_code=429)):
        with pytest.raises(InvokeError):
            invoke(llm)


def test_non_streaming_reasoning_is_wrapped() -> None:
    llm = SarvamLargeLanguageModel(model_schemas=[])
    payload = chat_payload(content="OK", reasoning="think first")
    with patch("requests.post", return_value=FakeResponse(payload)):
        result = invoke(llm)

    assert result.message.content.startswith("<think>\nthink first\n</think>")
    assert result.message.content.endswith("OK")
    assert result.message.opaque_body["reasoning_content"] == "think first"


def test_streaming_reasoning_is_wrapped() -> None:
    llm = SarvamLargeLanguageModel(model_schemas=[])
    chunks = [
        b'data: {"id":"x","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"reasoning_content":"think"},"finish_reason":null}]}\n\n',
        b'data: {"id":"x","object":"chat.completion.chunk","choices":[{"index":0,"delta":{"content":"OK"},"finish_reason":"stop"}]}\n\n',
        b"data: [DONE]\n\n",
    ]
    response = FakeResponse(content_type="text/event-stream", chunks=chunks)
    with patch("requests.post", return_value=response):
        result = list(invoke(llm, stream=True))

    text = "".join(chunk.delta.message.content or "" for chunk in result)
    assert "<think>" in text
    assert "think" in text
    assert "OK" in text


def test_tools_are_sent() -> None:
    llm = SarvamLargeLanguageModel(model_schemas=[])
    tool = PromptMessageTool(
        name="ping",
        description="Ping",
        parameters={"type": "object", "properties": {}},
    )
    with patch("requests.post", return_value=FakeResponse(chat_payload())) as post:
        invoke(llm, tools=[tool])

    _, kwargs = post.call_args
    body = json.loads(kwargs["data"])
    assert body["tools"][0]["function"]["name"] == "ping"
    assert body["tool_choice"] == "auto"


def test_assistant_think_block_is_stripped() -> None:
    llm = SarvamLargeLanguageModel(model_schemas=[])
    message = AssistantPromptMessage(content="<think>\nreasoning\n</think>answer")
    converted = llm._convert_prompt_message_to_dict(message, {})
    assert converted["content"] == "answer"

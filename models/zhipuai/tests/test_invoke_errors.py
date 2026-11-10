import json
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import yaml
from dify_plugin.entities.model import AIModelEntity
from dify_plugin.entities.model.message import UserPromptMessage
from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)
from zai import ZhipuAiClient

PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

from models.llm.llm import ZhipuAILargeLanguageModel
from models.text_embedding.text_embedding import ZhipuAITextEmbeddingModel

PROVIDER_MESSAGE = "余额不足，请充值。\n" + "Provider explanation. " * 50
ERROR_BODY = {
    "error": {
        "code": "1308",
        "message": PROVIDER_MESSAGE,
        "details": "raw-response-detail",
    }
}
PARTIAL_CHUNK = {
    "id": "test",
    "object": "chat.completion.chunk",
    "created": 1,
    "model": "glm-4.5",
    "choices": [
        {
            "index": 0,
            "delta": {"role": "assistant", "content": "Partial response"},
            "finish_reason": None,
        }
    ],
}


@pytest.fixture
def llm():
    schema = yaml.safe_load((PLUGIN_DIR / "models/llm/glm-4.5.yaml").read_text())
    return ZhipuAILargeLanguageModel([AIModelEntity.model_validate(schema)])


@contextmanager
def mock_transport(handler, module="models.llm.llm"):
    with httpx.Client(transport=httpx.MockTransport(handler)) as transport:
        client = ZhipuAiClient(
            api_key="test-key",
            base_url="https://example.com/v4/",
            http_client=transport,
            max_retries=0,
        )
        with patch(f"{module}.ZhipuAiClient", return_value=client):
            yield


def invoke(llm, stream=True):
    return llm.invoke(
        model="glm-4.5",
        credentials={"api_key": "test-key"},
        prompt_messages=[UserPromptMessage(content="Hello")],
        model_parameters={},
        stream=stream,
    )


@pytest.mark.parametrize("mode", ["stream", "non_stream", "embedding"])
@pytest.mark.parametrize(
    ("status", "expected_error"),
    [
        (400, InvokeBadRequestError),
        (401, InvokeAuthorizationError),
        (403, InvokeAuthorizationError),
        (429, InvokeRateLimitError),
        (500, InvokeServerUnavailableError),
        (503, InvokeServerUnavailableError),
    ],
)
def test_http_errors_preserve_only_provider_message(llm, mode, status, expected_error):
    module = (
        "models.text_embedding.text_embedding"
        if mode == "embedding"
        else "models.llm.llm"
    )
    with (
        mock_transport(lambda _: httpx.Response(status, json=ERROR_BODY), module),
        pytest.raises(expected_error) as raised,
    ):
        if mode == "embedding":
            ZhipuAITextEmbeddingModel([]).invoke(
                model="embedding-3",
                credentials={"api_key": "test-key"},
                texts=["Hello"],
            )
        else:
            list(invoke(llm, stream=mode == "stream"))

    assert str(raised.value) == f"[zhipuai] {PROVIDER_MESSAGE}"


@pytest.mark.parametrize("after_chunk", [False, True])
@pytest.mark.parametrize("event", ["", "event: error\n"])
def test_stream_errors_preserve_message_from_json_data(llm, after_chunk, event):
    body = f"data: {json.dumps(PARTIAL_CHUNK)}\n\n" if after_chunk else ""
    body += f"{event}data: {json.dumps(ERROR_BODY)}\n\n"
    with mock_transport(
        lambda _: httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=body
        )
    ):
        result = invoke(llm)
        if after_chunk:
            assert next(result).delta.message.content == "Partial response"
        with pytest.raises(InvokeBadRequestError) as raised:
            next(result)

    assert str(raised.value) == f"[zhipuai] {PROVIDER_MESSAGE}"


@pytest.mark.parametrize("error_class", [httpx.ConnectError, httpx.ReadTimeout])
def test_connection_errors_are_normalized(llm, error_class):
    def handler(request):
        raise error_class("network unavailable", request=request)

    with mock_transport(handler), pytest.raises(InvokeConnectionError):
        list(invoke(llm))


def test_connection_error_during_stream_is_normalized(llm):
    class BrokenStream(httpx.SyncByteStream):
        def __iter__(self):
            yield f"data: {json.dumps(PARTIAL_CHUNK)}\n\n".encode()
            raise httpx.ReadError("stream disconnected")

    with mock_transport(
        lambda _: httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=BrokenStream()
        )
    ):
        result = invoke(llm)
        assert next(result).delta.message.content == "Partial response"
        with pytest.raises(InvokeConnectionError, match="stream disconnected"):
            next(result)


@pytest.mark.parametrize(
    "body",
    [
        "<html>raw-response-detail</html>",
        '{"error":{"message":null,"details":"raw-response-detail"}}',
        '{"error":{"message":{"detail":"raw-response-detail"}}}',
    ],
)
def test_missing_http_message_does_not_expose_response_body(llm, body):
    with (
        mock_transport(lambda _: httpx.Response(503, content=body)),
        pytest.raises(InvokeServerUnavailableError) as raised,
    ):
        list(invoke(llm))

    assert str(raised.value) == "[zhipuai] ZHIPU AI API request failed (HTTP 503)."


@pytest.mark.parametrize("during_iteration", [False, True])
def test_existing_invoke_error_is_preserved(llm, during_iteration):
    error = InvokeBadRequestError("Invalid prompt")

    def response():
        yield from ()
        raise error

    with patch.object(llm, "_generate") as generate:
        if during_iteration:
            generate.return_value = response()
        else:
            generate.side_effect = error
        with pytest.raises(InvokeBadRequestError) as raised:
            list(invoke(llm))

    assert raised.value is error

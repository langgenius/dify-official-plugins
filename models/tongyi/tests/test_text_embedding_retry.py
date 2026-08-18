"""Regression tests for connection handling in the Tongyi text embedding model.

`call_embedding_api` used to catch every exception and return the exception object
as if it were a response. A connection-level failure carries no `status_code` and no
`output`, so it fell through to the "Response output is missing or does not contain
embeddings" ValueError with the exception repr embedded, and only HTTP 429 was ever
retried. That misclassified transient network faults as malformed responses, which
also meant `_transform_invoke_error` could never map them to a connection error.

These tests pin the corrected behaviour:
- transient connection failures are retried with a bounded backoff and then succeed,
- persistent failures re-raise the ORIGINAL exception rather than a ValueError,
- the malformed-response ValueError still fires for genuinely malformed but
  successful responses,
- the pre-existing 429 retry path is unchanged,
- a connection error maps to InvokeConnectionError through the tongyi mapping.

Everything here is offline by construction: the dashscope call boundary is
monkeypatched, so no credentials and no network I/O are required. Sleeps are captured
rather than performed, so the module runs in well under a second.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests
from dify_plugin.entities.model.text_embedding import (
    MultiModalContent,
    MultiModalContentType,
)
from dify_plugin.errors.model import InvokeConnectionError

# Make the plugin's own modules importable when pytest is invoked from the
# plugin directory or the repo root, matching the pattern in the other
# models/tongyi/tests/ files.
_PLUGIN_DIR = Path(__file__).resolve().parent.parent
if str(_PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_DIR))

from models.text_embedding import text_embedding as te  # noqa: E402

TongyiTextEmbeddingModel = te.TongyiTextEmbeddingModel

CREDENTIALS = {"dashscope_api_key": "test-key"}
BASE_ADDRESS = "https://dashscope.aliyuncs.com/api/v1"
TEXT_MODEL = "text-embedding-v3"
MULTIMODAL_MODEL = "multimodal-embedding-v1"

# The exact error the DashScope SDK lets propagate when the remote end closes the
# connection: requests raises ConnectionError wrapping http.client.RemoteDisconnected.
# Reproduced verbatim from the report in dify-official-plugins issue 3622.
CONNECTION_ABORTED_MESSAGE = (
    "('Connection aborted.', "
    "RemoteDisconnected('Remote end closed connection without response'))"
)


def _connection_error() -> requests.exceptions.ConnectionError:
    return requests.exceptions.ConnectionError(CONNECTION_ABORTED_MESSAGE)


class _TextResponse:
    """A realistic successful DashScope text-embedding response."""

    def __init__(self) -> None:
        self.status_code = 200
        self.output = {"embeddings": [{"embedding": [0.1, 0.2, 0.3], "type": "text"}]}
        self.usage = {"total_tokens": 7}


class _MultiModalResponse:
    """A realistic successful DashScope multimodal-embedding response."""

    def __init__(self) -> None:
        self.status_code = 200
        self.output = {"embeddings": [{"embedding": [0.4, 0.5], "type": "text"}]}
        self.usage = {"input_tokens": 5, "image_tokens": 0}


class _MalformedResponse:
    """A SUCCESSFUL response whose payload carries no embeddings."""

    def __init__(self) -> None:
        self.status_code = 200
        self.output = {"embeddings": []}
        self.usage = {"total_tokens": 1}


class _RateLimitedResponse:
    """DashScope surfaces HTTP 429 as a response object, not as an exception."""

    def __init__(self) -> None:
        self.status_code = 429
        self.output = None
        self.usage = None


class _Caller:
    """Stands in for the dashscope call, counting invocations.

    Raises `error` for the first `failures` calls (or forever when `failures` is
    None), then returns `response`.
    """

    def __init__(self, response=None, error=None, failures=0):
        self.response = response
        self.error = error
        self.failures = failures
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.error is not None and (self.failures is None or self.calls <= self.failures):
            raise self.error
        return self.response


class _Sequence:
    """Returns queued responses in order, counting invocations."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return self.responses.pop(0)


@pytest.fixture
def sleeps(monkeypatch) -> list:
    """Capture backoff durations instead of waiting them out.

    Returns the list of seconds passed to time.sleep, so tests can assert the
    retry schedule as well as the retry count.
    """
    recorded: list = []
    monkeypatch.setattr(te.time, "sleep", recorded.append)
    return recorded


def _embed_documents():
    return TongyiTextEmbeddingModel.embed_documents(
        credentials_kwargs=CREDENTIALS,
        model=TEXT_MODEL,
        texts=["hello"],
        base_address=BASE_ADDRESS,
    )


def _embed_multimodal_documents():
    documents = [MultiModalContent(content_type=MultiModalContentType.TEXT, content="hello")]
    return TongyiTextEmbeddingModel.embed_multimodal_documents(
        credentials_kwargs=CREDENTIALS,
        model=MULTIMODAL_MODEL,
        documents=documents,
        base_address=BASE_ADDRESS,
    )


def test_successful_call_is_not_retried(monkeypatch, sleeps) -> None:
    """A response that arrives first time must cost exactly one API call."""
    caller = _Caller(response=_TextResponse())
    monkeypatch.setattr(te.dashscope.TextEmbedding, "call", caller)

    assert _embed_documents() == ([[0.1, 0.2, 0.3]], 7)
    assert caller.calls == 1
    assert sleeps == []


def test_transient_connection_error_is_retried_then_succeeds(monkeypatch, sleeps) -> None:
    """One transient blip -- the reporter's scenario -- must no longer be fatal."""
    caller = _Caller(response=_TextResponse(), error=_connection_error(), failures=1)
    monkeypatch.setattr(te.dashscope.TextEmbedding, "call", caller)

    assert _embed_documents() == ([[0.1, 0.2, 0.3]], 7)
    assert caller.calls == 2
    assert sleeps == [1]


def test_transient_connection_error_is_retried_for_multimodal(monkeypatch, sleeps) -> None:
    """embed_multimodal_documents duplicated the pattern and must behave identically."""
    caller = _Caller(response=_MultiModalResponse(), error=_connection_error(), failures=1)
    monkeypatch.setattr(te.dashscope.MultiModalEmbedding, "call", caller)

    assert _embed_multimodal_documents() == ([[0.4, 0.5]], 5)
    assert caller.calls == 2
    assert sleeps == [1]


def test_transient_timeout_is_retried_then_succeeds(monkeypatch, sleeps) -> None:
    """Timeouts are the same class of transient transport fault as a dropped
    connection, and the SDK raises them equally unwrapped.
    """
    caller = _Caller(
        response=_TextResponse(),
        error=requests.exceptions.Timeout("timed out"),
        failures=1,
    )
    monkeypatch.setattr(te.dashscope.TextEmbedding, "call", caller)

    assert _embed_documents() == ([[0.1, 0.2, 0.3]], 7)
    assert caller.calls == 2


def test_persistent_connection_error_reraises_original_exception(monkeypatch, sleeps) -> None:
    """Once retries are exhausted the ORIGINAL exception must propagate.

    This is the core of the bug: it previously surfaced as a ValueError about a
    malformed response, which hid the real cause and defeated the SDK's error
    taxonomy. Asserting the type (not just the message) is the point.
    """
    error = _connection_error()
    caller = _Caller(error=error, failures=None)
    monkeypatch.setattr(te.dashscope.TextEmbedding, "call", caller)

    with pytest.raises(requests.exceptions.ConnectionError) as excinfo:
        _embed_documents()

    assert excinfo.value is error
    assert not isinstance(excinfo.value, ValueError)
    # One initial attempt plus two retries, with the 1s/3s backoff schedule.
    assert caller.calls == 3
    assert sleeps == [1, 3]


def test_persistent_connection_error_reraises_for_multimodal(monkeypatch, sleeps) -> None:
    """Same guarantee for the multimodal path."""
    error = _connection_error()
    caller = _Caller(error=error, failures=None)
    monkeypatch.setattr(te.dashscope.MultiModalEmbedding, "call", caller)

    with pytest.raises(requests.exceptions.ConnectionError) as excinfo:
        _embed_multimodal_documents()

    assert excinfo.value is error
    assert caller.calls == 3
    assert sleeps == [1, 3]


def test_malformed_successful_response_still_raises_value_error(monkeypatch, sleeps) -> None:
    """The ValueError was narrowed, not removed: a successful response carrying no
    embeddings is still a malformed response and must still be reported as one.
    """
    caller = _Caller(response=_MalformedResponse())
    monkeypatch.setattr(te.dashscope.TextEmbedding, "call", caller)

    with pytest.raises(ValueError, match="Response output is missing"):
        _embed_documents()

    # A malformed payload is not a transport fault, so it must not be retried.
    assert caller.calls == 1


def test_rate_limit_429_retry_path_is_unchanged(monkeypatch, sleeps) -> None:
    """429 arrives as a response object, so it must keep using the pre-existing
    single retry after a 10s sleep rather than the connection-error retry.
    """
    caller = _Sequence([_RateLimitedResponse(), _TextResponse()])
    monkeypatch.setattr(te.dashscope.TextEmbedding, "call", caller)

    assert _embed_documents() == ([[0.1, 0.2, 0.3]], 7)
    assert caller.calls == 2
    assert sleeps == [10]


def test_connection_error_maps_to_invoke_connection_error() -> None:
    """The re-raised exception must land in the connection bucket of the provider
    error mapping; without it the SDK falls back to a generic InvokeError.
    """
    model = TongyiTextEmbeddingModel(model_schemas=MagicMock())

    mapped = model._transform_invoke_error(_connection_error())

    assert isinstance(mapped, InvokeConnectionError)


def test_timeout_maps_to_invoke_connection_error() -> None:
    """Timeouts must be classified as connection errors too."""
    model = TongyiTextEmbeddingModel(model_schemas=MagicMock())

    mapped = model._transform_invoke_error(requests.exceptions.Timeout("timed out"))

    assert isinstance(mapped, InvokeConnectionError)

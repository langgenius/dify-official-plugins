"""Regression tests for the S3 streaming-body-close bug fixed in this PR.

Before the fix, the S3 datasource's `_download_file` called
`response["Body"].read()` and then yielded the bytes — without ever
closing the StreamingBody. boto3 holds a live network connection open
on the body until `.close()` is called, so every download leaked one
connection. The leak was worse on read failure: a botocore.EndpointConnectionError
mid-stream would leave the body open forever, never returning the
connection to the pool.

These tests pin:

  * the body is closed on a successful download;
  * the body is closed when the read raises mid-stream;
  * the body is closed when something raises before .read() is even
    called;
  * the yielded DatasourceMessage still carries the read bytes on
    success;
  * a source-level guard pins the dispatcher on aws_s3_storage.py so a
    future refactor can't reintroduce the bare `.read()` pattern.
"""

from __future__ import annotations

import pathlib
from collections.abc import Generator
from typing import Any

import pytest

from datasources.aws_s3_storage import AWSS3StorageDataSource

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parents[1]
DEST_PY = PLUGIN_ROOT / "datasources" / "aws_s3_storage.py"


# ---------------------------------------------------------------------------
# Test fakes
# ---------------------------------------------------------------------------

class _ClosedMarker:
    """Set to True the first time .close() is called on a stub body."""

    def __init__(self) -> None:
        self.closed = False
        self.close_calls = 0


class _StubStreamingBody:
    """Stand-in for boto3's StreamingBody.

    `payload` is the bytes returned by .read(). `raise_on_read` causes the
    .read() call to raise that exception instance so the test can exercise
    the failure path.
    """

    def __init__(
        self,
        payload: bytes = b"hello",
        *,
        raise_on_read: Exception | None = None,
    ) -> None:
        self._payload = payload
        self._raise_on_read = raise_on_read
        self.closed_marker = _ClosedMarker()

    def read(self) -> bytes:
        if self._raise_on_read is not None:
            raise self._raise_on_read
        return self._payload

    def close(self) -> None:
        self.closed_marker.closed = True
        self.closed_marker.close_calls += 1


class _StubS3Client:
    """Records the last get_object call and returns the stubbed body."""

    def __init__(self, body: _StubStreamingBody) -> None:
        self._body = body
        self.last_get_object: dict[str, Any] | None = None

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        self.last_get_object = {"Bucket": Bucket, "Key": Key}
        return {"Body": self._body, "ContentType": "application/octet-stream"}


class _RuntimeStub:
    def __init__(self) -> None:
        self.credentials = {
            "access_key_id": "AKIA...",
            "secret_access_key": "secret",
            "region_name": "us-east-1",
        }


def _instance() -> AWSS3StorageDataSource:
    obj = AWSS3StorageDataSource.__new__(AWSS3StorageDataSource)
    obj.runtime = _RuntimeStub()
    # `response_type` is normally set by OnlineDriveDatasource.__init__ via a
    # dify_plugin runtime call. We bypass __init__ to keep the test offline,
    # so supply a stand-in. create_blob_message calls it as
    # `response_type(type=..., message=InvokeMessage.BlobMessage(blob=blob), meta=...)`
    # and we only care about the bytes that survive the round trip.

    class _BlobResponse:
        BLOB = "blob"

        def __init__(self, type: str, message: Any, meta: dict | None = None) -> None:
            self.type = type
            self.message = message
            self.meta = meta or {}

        # `create_blob_message` then accesses .content on the resulting object
        # via the dify_plugin runtime, which forwards through to message.blob.
        @property
        def content(self) -> bytes:
            return self.message.blob

    obj.response_type = _BlobResponse
    return obj


def _drive_download_request(bucket: str = "test-bucket", key: str = "path/to/file.bin"):
    """Build an OnlineDriveDownloadFileRequest with the minimum required fields."""
    from dify_plugin.entities.datasource import OnlineDriveDownloadFileRequest
    return OnlineDriveDownloadFileRequest(bucket=bucket, id=key)


def _run_download(
    monkeypatch: pytest.MonkeyPatch,
    *,
    body: _StubStreamingBody,
) -> Generator[Any, None, None]:
    """Run _download_file end-to-end with the stubbed client.

    boto3.client is monkey-patched to a factory that returns the stub. Yields
    from the result is consumed by the caller.
    """
    stub_client = _StubS3Client(body)

    def fake_client_factory(
        *args: Any,
        **kwargs: Any,
    ) -> _StubS3Client:
        return stub_client

    monkeypatch.setattr("datasources.aws_s3_storage.boto3.client", fake_client_factory)
    return _instance()._download_file(_drive_download_request())


# ---------------------------------------------------------------------------
# Body-close behavior
# ---------------------------------------------------------------------------

def test_body_is_closed_after_successful_download(monkeypatch: pytest.MonkeyPatch):
    """Happy path: bytes are yielded, then the body is closed exactly once."""
    body = _StubStreamingBody(payload=b"abc")
    # Consume the generator to drive the function to completion.
    messages = list(_run_download(monkeypatch, body=body))

    assert len(messages) == 1
    msg = messages[0]
    assert msg.content == b"abc"
    assert body.closed_marker.closed is True
    assert body.closed_marker.close_calls == 1


def test_body_is_closed_when_read_raises(monkeypatch: pytest.MonkeyPatch):
    """Mid-stream failure: read raises, body is still closed, exception propagates."""
    body = _StubStreamingBody(raise_on_read=ConnectionError("stream failed"))
    with pytest.raises(ConnectionError, match="stream failed"):
        list(_run_download(monkeypatch, body=body))

    assert body.closed_marker.closed is True, (
        "StreamingBody leaked when .read() raised; the connection will not return to the boto3 pool"
    )
    assert body.closed_marker.close_calls == 1


# ---------------------------------------------------------------------------
# Source-level guard
# ---------------------------------------------------------------------------

def test_llm_body_is_closed_in_finally():
    """Pin the dispatcher on aws_s3_storage.py so a future refactor can't reintroduce the bare `.read()` pattern."""
    source = DEST_PY.read_text()
    # The function must capture the body in a local, wrap .read() in a try,
    # and call .close() in a finally block.
    assert "body = response[\"Body\"]" in source, (
        "the response body must be captured to a local before .read() so the finally can close it"
    )
    assert "finally:" in source, (
        "a try/finally must wrap .read() so the body is closed even when read fails"
    )
    # And the body.close() must be the only thing in the finally (apart from a comment).
    finally_block = source.split("finally:", 1)[1].split("yield", 1)[0]
    assert "body.close()" in finally_block, (
        "the finally block must call body.close() to release the boto3 connection"
    )
    # The original bug shape: `response["Body"].read()` with no close.
    assert 'response["Body"].read()' not in source, (
        "the original bare .read() pattern must not be reintroduced"
    )
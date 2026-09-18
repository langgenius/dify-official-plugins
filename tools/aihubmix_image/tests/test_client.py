"""Client-level concerns: where the API key is allowed to travel."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils import client as client_module  # noqa: E402
from utils.client import AIHubMixClient, GatewayError  # noqa: E402


class FakeResponse:
    def __init__(self, status_code=200, content=b"", *, payload=None):
        self.status_code = status_code
        self.content = content
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


@pytest.fixture
def recorder(monkeypatch):
    """Captures every outbound request and replays queued responses."""
    calls: list[dict] = []
    queue: list[FakeResponse] = []

    def fake_request(method, url, *, headers=None, json=None, timeout=None):
        calls.append({"method": method, "url": url, "headers": headers or {}})
        return queue.pop(0) if queue else FakeResponse()

    monkeypatch.setattr(client_module.requests, "request", fake_request)
    return calls, queue


def make_client():
    return AIHubMixClient({"api_key": "sk-test"})


def test_gateway_url_recognition():
    client = make_client()
    assert client.is_gateway_url("/ai/v1/images/task_1")
    assert client.is_gateway_url("https://api.inferera.com/ai/v1/images/task_1")
    # The gateway answers an api.inferera.com call with aihubmix.com artifact links.
    assert client.is_gateway_url("https://aihubmix.com/ai/v1/images/t_1/content/res_1")
    assert not client.is_gateway_url("http://qianfan-modelbuilder-img-gen.bj.bcebos.com/x.jpg")


def test_download_from_gateway_sends_the_key(recorder):
    calls, _queue = recorder
    make_client().get_bytes("https://api.inferera.com/ai/v1/images/task_1/content")
    assert calls[0]["headers"]["Authorization"] == "Bearer sk-test"


def test_download_from_vendor_cdn_omits_the_key(recorder):
    # Baidu BOS parses Authorization as its own signature scheme and answers 400
    # MissingDateHeader when it sees a bearer token.
    calls, _queue = recorder
    make_client().get_bytes("http://qianfan-modelbuilder-img-gen.bj.bcebos.com/out.jpg")
    assert "Authorization" not in calls[0]["headers"]
    assert len(calls) == 1


def test_unauthenticated_download_retries_with_the_key_on_403(recorder):
    calls, queue = recorder
    queue.extend([FakeResponse(403), FakeResponse(200, b"bytes")])
    assert make_client().get_bytes("https://cdn.example.com/out.png") == b"bytes"
    assert "Authorization" not in calls[0]["headers"]
    assert calls[1]["headers"]["Authorization"] == "Bearer sk-test"


def test_download_failure_carries_the_gateway_error(recorder):
    _calls, queue = recorder
    queue.append(FakeResponse(410, payload={"error": {"message": "expired", "code": "gone"}}))
    with pytest.raises(GatewayError) as excinfo:
        make_client().get_bytes("/ai/v1/images/task_1/content")
    assert excinfo.value.code == "gone"

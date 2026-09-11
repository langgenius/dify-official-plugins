"""Task lifecycle: polling to a terminal state, collecting artifacts, sniffing the type."""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils import task  # noqa: E402
from utils.client import GatewayError  # noqa: E402
from utils.schema import ImageEndpoint  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 "

ENDPOINT = ImageEndpoint(
    model="gpt-image-2",
    display_name="GPT Image 2",
    path="/ai/v1/images/generations",
    method="POST",
    mode="sync",
    poll_path="/ai/v1/images/{id}",
    poll_method="GET",
    status_values=("pending", "in_progress", "completed", "failed", "cancelled"),
    supports_async=False,
    schema={},
)


class FakeClient:
    """Stands in for AIHubMixClient; records what was asked for."""

    def __init__(self, *, responses, blobs=None):
        self.responses = list(responses)
        self.blobs = blobs or {}
        self.downloaded: list[str] = []
        self.polled: list[str] = []
        self.posted: list[dict] = []

    def post_json(self, path, payload, **kwargs):
        self.posted.append(payload)
        return self.responses.pop(0)

    def get_json(self, path, **kwargs):
        self.polled.append(path)
        return self.responses.pop(0)

    def get_bytes(self, url, **kwargs):
        self.downloaded.append(url)
        if url not in self.blobs:
            raise GatewayError("not found", status=404)
        return self.blobs[url]


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    monkeypatch.setattr(task.time, "sleep", lambda _seconds: None)


def test_sync_completed_task_downloads_content_url():
    client = FakeClient(
        responses=[
            {
                "id": "img_1",
                "model": "gpt-image-2",
                "status": "completed",
                "expires_at": 1750000000,
                "output": [{"index": 0, "type": "image", "content_url": "https://x/img_1.png"}],
            }
        ],
        blobs={"https://x/img_1.png": PNG},
    )
    result = task.run(client, ENDPOINT, {"model": "gpt-image-2", "prompt": "hi"})

    assert result.status == "completed"
    assert result.task_id == "img_1"
    assert result.expires_at == 1750000000
    assert client.downloaded == ["https://x/img_1.png"]
    assert result.images[0].mime_type == "image/png"


def test_pending_task_is_polled_until_terminal():
    client = FakeClient(
        responses=[
            {"id": "img_2", "status": "pending"},
            {"id": "img_2", "status": "in_progress"},
            {
                "id": "img_2",
                "status": "completed",
                "output": [{"content_url": "https://x/img_2"}],
            },
        ],
        blobs={"https://x/img_2": JPEG},
    )
    result = task.run(client, ENDPOINT, {"model": "gpt-image-2", "prompt": "hi"})

    assert client.polled == ["/ai/v1/images/img_2", "/ai/v1/images/img_2"]
    assert result.polls == 2
    assert result.images[0].extension == "jpg"


def test_failed_task_surfaces_the_gateway_error():
    client = FakeClient(
        responses=[
            {
                "id": "img_3",
                "status": "failed",
                "error": {"message": "content policy violation", "code": "moderation_blocked"},
            }
        ]
    )
    with pytest.raises(GatewayError) as excinfo:
        task.run(client, ENDPOINT, {"model": "gpt-image-2", "prompt": "hi"})
    assert "content policy" in str(excinfo.value)


def test_b64_output_needs_no_download():
    client = FakeClient(
        responses=[
            {"id": "img_4", "status": "completed", "output": [{"b64_json": base64.b64encode(WEBP).decode()}]}
        ]
    )
    result = task.run(client, ENDPOINT, {"model": "gpt-image-2", "prompt": "hi"})

    assert client.downloaded == []
    assert result.images[0].mime_type == "image/webp"


def test_legacy_openai_shape_is_still_understood():
    # Older gateway builds answered image calls with the OpenAI body and no status field.
    client = FakeClient(
        responses=[{"created": 1, "data": [{"url": "https://x/legacy.png"}]}],
        blobs={"https://x/legacy.png": PNG},
    )
    result = task.run(client, ENDPOINT, {"model": "gpt-image-2", "prompt": "hi"})

    assert client.polled == []
    assert len(result.images) == 1


def test_completed_task_without_output_is_an_error():
    client = FakeClient(responses=[{"id": "img_5", "status": "completed", "output": []}])
    with pytest.raises(GatewayError) as excinfo:
        task.run(client, ENDPOINT, {"model": "gpt-image-2", "prompt": "hi"})
    assert "no image data" in str(excinfo.value)


def test_expired_artifact_explains_the_two_hour_window():
    client = FakeClient(
        responses=[{"id": "img_6", "status": "completed", "output": [{"content_url": "https://x/gone"}]}],
    )
    client.blobs = {}

    def gone(url, **kwargs):
        raise GatewayError("expired", status=410)

    client.get_bytes = gone
    with pytest.raises(GatewayError) as excinfo:
        task.run(client, ENDPOINT, {"model": "gpt-image-2", "prompt": "hi"})
    assert "expired" in str(excinfo.value)


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (PNG, ("image/png", "png")),
        (JPEG, ("image/jpeg", "jpg")),
        (WEBP, ("image/webp", "webp")),
        (b"GIF89a\x00", ("image/gif", "gif")),
        (b"\x00\x00\x00\x20ftypavif", ("image/avif", "avif")),
        (b"whatever", ("application/octet-stream", "bin")),
    ],
)
def test_type_is_sniffed_from_the_bytes(data, expected):
    # The gateway labels everything image/png, so the header cannot be trusted.
    assert task.sniff_image_type(data) == expected


def test_polling_budget_is_reported_rather_than_hanging():
    client = FakeClient(responses=[{"id": "img_7", "status": "pending"}])
    with pytest.raises(GatewayError) as excinfo:
        task.run(client, ENDPOINT, {"model": "gpt-image-2", "prompt": "hi"}, poll_budget=0)
    assert "img_7" in str(excinfo.value)


def test_submission_never_opts_into_the_async_task_path():
    # The async path is advertised by every image endpoint but fails delivery on some models,
    # so the request must go out exactly as build_payload produced it.
    endpoint = ImageEndpoint(**{**ENDPOINT.__dict__, "supports_async": True,
                                "schema": {"properties": {"async": {"type": "boolean"}}}})
    client = FakeClient(responses=[{"id": "t1", "status": "completed", "output": []}])
    task.submit(client, endpoint, {"model": "m", "prompt": "p"})
    assert client.posted[0] == {"model": "m", "prompt": "p"}

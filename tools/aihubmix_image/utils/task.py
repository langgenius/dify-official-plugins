"""Task submission, polling and artifact download for the unified image endpoint.

The gateway answers a generation request with a Task object::

    {"id": "...", "status": "completed", "output": [{"type": "image", "content_url": "..."}],
     "expires_at": 1750000000, "error": null}

``status`` may be non-terminal (``pending`` / ``in_progress``), in which case the endpoint
document's ``poll_path`` is polled until the task settles. Artifacts live behind
``content_url`` for two hours and need the API key, so this module downloads the bytes
itself rather than handing the URL to Dify (a browser fetching it without the Bearer header
gets 401).
"""

from __future__ import annotations

import base64
import binascii
import time
from dataclasses import dataclass, field
from typing import Any

from utils.client import AIHubMixClient, GatewayError, error_from_payload
from utils.schema import ImageEndpoint

TERMINAL_SUCCESS = {"completed", "succeeded", "success"}
TERMINAL_FAILURE = {"failed", "cancelled", "canceled", "error"}

POLL_INTERVAL = 2.0
POLL_BUDGET = 600.0

# The gateway labels every artifact image/png regardless of what the upstream model
# returned, so the extension comes from the bytes instead of the header.
_MAGIC: tuple[tuple[bytes, str, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"GIF87a", "image/gif", "gif"),
    (b"GIF89a", "image/gif", "gif"),
    (b"BM", "image/bmp", "bmp"),
    (b"II*\x00", "image/tiff", "tiff"),
    (b"MM\x00*", "image/tiff", "tiff"),
)


def sniff_image_type(data: bytes) -> tuple[str, str]:
    """Return ``(mime, extension)`` detected from the magic bytes."""
    for magic, mime, extension in _MAGIC:
        if data.startswith(magic):
            return mime, extension
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    if data[4:12] in (b"ftypavif", b"ftypavis"):
        return "image/avif", "avif"
    if data[4:8] == b"ftyp" and data[8:12] in (b"heic", b"heix", b"mif1", b"msf1"):
        return "image/heic", "heic"
    stripped = data.lstrip()[:256].lower()
    if stripped.startswith(b"<svg") or (stripped.startswith(b"<?xml") and b"<svg" in stripped):
        return "image/svg+xml", "svg"
    return "application/octet-stream", "bin"


@dataclass
class ImageArtifact:
    data: bytes
    mime_type: str
    extension: str


@dataclass
class TaskResult:
    task_id: str
    model: str
    status: str
    images: list[ImageArtifact] = field(default_factory=list)
    expires_at: int | None = None
    polls: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


def submit(client: AIHubMixClient, endpoint: ImageEndpoint, payload: dict[str, Any]) -> dict[str, Any]:
    return client.post_json(endpoint.path, payload)


def run(
    client: AIHubMixClient,
    endpoint: ImageEndpoint,
    payload: dict[str, Any],
    *,
    poll_budget: float = POLL_BUDGET,
) -> TaskResult:
    """Submit the request, wait for a terminal status, and download every artifact."""
    task = submit(client, endpoint, payload)
    task, polls = _await_terminal(client, endpoint, task, poll_budget=poll_budget)

    status = _status_of(task)
    if status in TERMINAL_FAILURE:
        raise error_from_payload(
            task,
            fallback=f"Image task {_task_id(task)} ended with status '{status}'",
        )

    images = _collect_images(client, task)
    if not images:
        raise GatewayError(
            f"Image task {_task_id(task)} reported '{status}' but returned no image data"
        )

    expires_at = task.get("expires_at")
    return TaskResult(
        task_id=_task_id(task),
        model=str(task.get("model") or payload.get("model") or endpoint.model),
        status=status or "completed",
        images=images,
        expires_at=int(expires_at) if isinstance(expires_at, (int, float)) else None,
        polls=polls,
        raw=task,
    )


def _status_of(task: Any) -> str:
    if not isinstance(task, dict):
        return ""
    return str(task.get("status") or "").lower()


def _task_id(task: Any) -> str:
    return str(task.get("id") or "") if isinstance(task, dict) else ""


def _await_terminal(
    client: AIHubMixClient,
    endpoint: ImageEndpoint,
    task: dict[str, Any],
    *,
    poll_budget: float,
) -> tuple[dict[str, Any], int]:
    status = _status_of(task)
    # A synchronous endpoint answers with the finished task, and a response with no status
    # at all is one of the legacy OpenAI-style bodies — neither is pollable.
    if not status or status in TERMINAL_SUCCESS or status in TERMINAL_FAILURE:
        return task, 0

    task_id = _task_id(task)
    poll_path = (endpoint.poll_path or "/ai/v1/images/{id}").replace("{id}", task_id)
    if not task_id:
        raise GatewayError(f"Task is '{status}' but carries no id to poll")

    deadline = time.monotonic() + poll_budget
    polls = 0
    while time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL)
        polled = client.get_json(poll_path)
        polls += 1
        if isinstance(polled, dict):
            task = polled
            status = _status_of(task)
            if status in TERMINAL_SUCCESS or status in TERMINAL_FAILURE:
                return task, polls

    raise GatewayError(
        f"Image task {task_id} was still '{status}' after {int(poll_budget)}s; "
        f"it may finish later — retry with the same prompt or check the AIHubMix console"
    )


def _collect_images(client: AIHubMixClient, task: dict[str, Any]) -> list[ImageArtifact]:
    images: list[ImageArtifact] = []
    for item in _output_items(task):
        artifact = _artifact_from(client, item)
        if artifact is not None:
            images.append(artifact)
    return images


def _output_items(task: dict[str, Any]) -> list[Any]:
    """Flatten the unified ``output`` list and the legacy shapes into one item list."""
    items: list[Any] = []
    for key in ("output", "data", "images"):
        value = task.get(key)
        if isinstance(value, list):
            items.extend(value)
        elif isinstance(value, dict):
            items.append(value)
        elif isinstance(value, str) and value:
            items.append(value)
    if not items:
        for key in ("url", "image_url", "b64_json"):
            value = task.get(key)
            if isinstance(value, str) and value:
                items.append({key: value})
    return items


def _artifact_from(client: AIHubMixClient, item: Any) -> ImageArtifact | None:
    if isinstance(item, str):
        return _download(client, item) if item.startswith(("http://", "https://")) else _decode(item)
    if not isinstance(item, dict):
        return None

    for key in ("b64_json", "base64", "image_base64", "data"):
        value = item.get(key)
        if isinstance(value, str) and value and not value.startswith(("http://", "https://")):
            artifact = _decode(value)
            if artifact is not None:
                return artifact

    for key in ("content_url", "url", "image_url"):
        value = item.get(key)
        if isinstance(value, dict):
            value = value.get("url")
        if isinstance(value, str) and value:
            return _download(client, value)
    return None


def _download(client: AIHubMixClient, url: str) -> ImageArtifact:
    try:
        data = client.get_bytes(url)
    except GatewayError as exc:
        if exc.status == 410:
            raise GatewayError(
                "The generated image has already expired on the gateway (artifacts are kept "
                "for two hours); re-run the tool to generate a fresh one"
            ) from exc
        raise
    mime_type, extension = sniff_image_type(data)
    return ImageArtifact(data=data, mime_type=mime_type, extension=extension)


def _decode(value: str) -> ImageArtifact | None:
    payload = value.split(",", 1)[1] if value.startswith("data:") else value
    try:
        data = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError):
        return None
    if not data:
        return None
    mime_type, extension = sniff_image_type(data)
    return ImageArtifact(data=data, mime_type=mime_type, extension=extension)

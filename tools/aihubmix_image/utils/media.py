"""Turning Dify file parameters into media references the gateway accepts.

``x-media-ref`` fields take either an http(s) URL, a data URI, or raw base64. A Dify file
usually lives on the Dify instance's own storage, which the gateway cannot reach, so the
bytes are inlined as a data URI instead of forwarding the URL.
"""

from __future__ import annotations

import base64
from typing import Any

from utils.client import GatewayError
from utils.schema import ImageEndpoint

# Inlining is what makes private Dify storage work, but the request body is JSON, so a very
# large file would be base64-expanded into memory twice. 20 MiB matches the upstream limit.
MAX_INLINE_BYTES = 20 * 1024 * 1024


def to_reference(value: Any, *, label: str) -> str:
    """Normalise one file parameter into a string the media field accepts."""
    if isinstance(value, str):
        reference = value.strip()
        if not reference:
            raise GatewayError(f"{label} is empty")
        return reference

    blob = getattr(value, "blob", None)
    if not isinstance(blob, (bytes, bytearray)):
        url = getattr(value, "url", None)
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            return url
        raise GatewayError(f"{label} must be an uploaded image file or an image URL")

    if len(blob) > MAX_INLINE_BYTES:
        raise GatewayError(
            f"{label} is {len(blob) // (1024 * 1024)} MiB; the limit is "
            f"{MAX_INLINE_BYTES // (1024 * 1024)} MiB"
        )

    mime_type = getattr(value, "mime_type", None) or "image/png"
    return f"data:{mime_type};base64,{base64.b64encode(bytes(blob)).decode('ascii')}"


def as_list(value: Any) -> list[Any]:
    if value in (None, "", []):
        return []
    return list(value) if isinstance(value, list) else [value]


def source_images(endpoint: ImageEndpoint, files: Any, *, label: str = "Image") -> dict[str, Any]:
    """Map uploaded files onto whichever media field this model declares.

    ``image`` and ``images`` are aliases upstream (``image == images[0]``), so a model that
    only declares one of them still gets the input.
    """
    items = as_list(files)
    if not items:
        return {}

    references = [to_reference(item, label=label) for item in items]

    if endpoint.declares("images"):
        limit = endpoint.properties["images"].get("maxItems")
        if isinstance(limit, int) and len(references) > limit:
            raise GatewayError(f"{endpoint.model} accepts at most {limit} input images")
        return {"images": references}
    if endpoint.declares("image"):
        if len(references) > 1:
            raise GatewayError(f"{endpoint.model} accepts a single input image")
        return {"image": references[0]}

    raise GatewayError(f"{endpoint.model} does not accept image input; use the generate tool")

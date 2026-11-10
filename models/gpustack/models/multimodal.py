"""GPUStack transport and typed image conversion for pooling models."""

import base64
import binascii
import math

import requests
from dify_plugin.entities.model.text_embedding import (
    MultiModalContent,
    MultiModalContentType,
)
from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)


def api_base_url(credentials: dict) -> str:
    base = credentials["endpoint_url"].strip().rstrip("/")
    return base.removesuffix("/v1").removesuffix("/v1-openai") + "/v1"


def image_data_uri(value: str) -> str:
    """Accept Dify base64 or a data URI and determine MIME from image bytes.

    Invalid content raises before a request is sent, so document positions are
    never changed by silently dropping an image.
    """
    encoded = value.strip()
    if encoded.startswith("data:"):
        header, separator, encoded = encoded.partition(",")
        if (
            not separator
            or not header.startswith("data:image/")
            or not header.endswith(";base64")
        ):
            raise InvokeBadRequestError("Expected a base64 image data URI")
    encoded = "".join(encoded.split())
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise InvokeBadRequestError("Invalid base64 image") from None
    signatures = (
        (b"\x89PNG\r\n\x1a\n", "png"),
        (b"\xff\xd8\xff", "jpeg"),
        (b"GIF87a", "gif"),
        (b"GIF89a", "gif"),
        (b"BM", "bmp"),
    )
    for signature, image_format in signatures:
        if data.startswith(signature):
            return f"data:image/{image_format};base64,{encoded}"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return f"data:image/webp;base64,{encoded}"
    raise InvokeBadRequestError(
        "Unsupported image format; use PNG, JPEG, GIF, WebP or BMP"
    )


def content_part(document: MultiModalContent) -> dict:
    if document.content_type == MultiModalContentType.TEXT:
        return {"type": "text", "text": document.content}
    if document.content_type == MultiModalContentType.IMAGE:
        return {
            "type": "image_url",
            "image_url": {"url": image_data_uri(document.content)},
        }
    raise InvokeBadRequestError("Unsupported multimodal content type")


def require_vision(credentials: dict) -> None:
    if credentials.get("vision_support") != "support":
        raise InvokeBadRequestError(
            "Enable Vision Support for this model before using multimodal inputs"
        )


def post_json(
    endpoint: str, credentials: dict, payload: dict, *, default_timeout: float = 600
) -> dict:
    """Send one request, translating errors without exposing media or credentials."""
    configured_timeout = credentials.get("timeout")
    if isinstance(configured_timeout, str):
        configured_timeout = configured_timeout.strip()
    if configured_timeout is None or configured_timeout == "":
        configured_timeout = default_timeout
    try:
        timeout = float(configured_timeout)
    except (TypeError, ValueError):
        raise InvokeBadRequestError("Timeout must be a positive number") from None
    if not math.isfinite(timeout) or timeout <= 0:
        raise InvokeBadRequestError("Timeout must be a positive number")
    headers = {"Content-Type": "application/json"}
    if credentials.get("api_key"):
        headers["Authorization"] = f"Bearer {credentials['api_key']}"
    response = None
    try:
        response = requests.post(
            endpoint, headers=headers, json=payload, timeout=timeout
        )
        response.raise_for_status()
        try:
            result = response.json()
        except ValueError:
            raise InvokeError("GPUStack returned invalid JSON") from None
        if not isinstance(result, dict):
            raise InvokeError("GPUStack returned an invalid JSON object")
        return result
    except requests.HTTPError as error:
        status = error.response.status_code if error.response is not None else 0
        message = f"GPUStack returned HTTP {status}"
        if status in (401, 403):
            raise InvokeAuthorizationError(message) from None
        if status == 429:
            raise InvokeRateLimitError(message) from None
        if 400 <= status < 500:
            raise InvokeBadRequestError(message) from None
        raise InvokeServerUnavailableError(message) from None
    except (requests.ConnectionError, requests.Timeout):
        raise InvokeConnectionError("GPUStack connection failed or timed out") from None
    except requests.RequestException:
        raise InvokeServerUnavailableError("GPUStack request failed") from None
    finally:
        if response is not None:
            response.close()

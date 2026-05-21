import base64
from typing import Any


def decode_image(base64_image: str) -> tuple[str, bytes]:
    """
    Decode an image payload. If the payload has no data URI prefix,
    default to PNG.
    """
    if not base64_image.startswith("data:image"):
        return ("image/png", base64.b64decode(base64_image))

    try:
        mime_type = base64_image.split(";")[0].split(":")[1]
        image_data_base64 = base64_image.split(",")[1]
        return (mime_type, base64.b64decode(image_data_base64))
    except (IndexError, ValueError):
        return ("image/png", base64.b64decode(base64_image.split(",")[-1]))


def build_usage_metadata(response: Any) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    usage = getattr(response, "usage", None)
    if not usage:
        return metadata

    usage_metadata: dict[str, Any] = {}
    if hasattr(usage, "total_tokens"):
        usage_metadata["total_tokens"] = usage.total_tokens
    if hasattr(usage, "input_tokens"):
        usage_metadata["input_tokens"] = usage.input_tokens
    if hasattr(usage, "output_tokens"):
        usage_metadata["output_tokens"] = usage.output_tokens

    details = getattr(usage, "input_tokens_details", None)
    if details:
        usage_metadata["input_tokens_details"] = {
            "text_tokens": getattr(details, "text_tokens", None),
            "image_tokens": getattr(details, "image_tokens", None),
        }

    if usage_metadata:
        metadata["token_usage"] = usage_metadata
    return metadata


def build_usage_output(response: Any, model: str, operation: str, image_count: int) -> dict[str, Any] | None:
    metadata = build_usage_metadata(response)
    token_usage = metadata.get("token_usage")
    if not token_usage:
        return None

    return {
        "data": [
            {
                "model": model,
                "operation": operation,
                "image_count": image_count,
                "usage": token_usage,
            }
        ]
    }

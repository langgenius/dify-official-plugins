import base64
import re
from typing import Any


def build_image_args(parameters: dict[str, Any]) -> dict[str, Any]:
    model = parameters.get("model", "gpt-image-2")
    if not isinstance(model, str) or model not in {
        "gpt-image-2",
        "gpt-image-2.5-flare",
        "gpt-image-2.5-sunburst",
    }:
        raise ValueError("Invalid model. Choose GPT Image 2, GPT Image 2.5 Flare, or Sunburst.")

    prompt = parameters.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("Please input prompt")
    args: dict[str, Any] = {"model": model, "prompt": prompt}

    size = parameters.get("size", "auto")
    if size != "auto":
        if not isinstance(size, str) or not re.fullmatch(r"[0-9]{1,4}x[0-9]{1,4}", size):
            raise ValueError("Invalid size. Use auto or WIDTHxHEIGHT.")
        width, height = map(int, size.split("x"))
        if (
            not (0 < width <= 3840 and 0 < height <= 3840)
            or width % 16
            or height % 16
            or max(width, height) > 3 * min(width, height)
            or not 655_360 <= width * height <= 8_294_400
        ):
            raise ValueError(
                "Invalid size. Dimensions must be multiples of 16, at most 3840 per edge, "
                "with aspect ratio between 1:3 and 3:1 and 655360–8294400 total pixels."
            )
        args["size"] = size

    qualities = {"auto", "low", "medium", "high"}
    if model != "gpt-image-2":
        qualities.update({"xhigh", "max"})
    for name, allowed in (
        ("quality", qualities),
        ("background", {"auto", "opaque", "transparent"}),
        ("output_format", {"auto", "png", "jpeg", "webp"}),
    ):
        value = parameters.get(name, "auto")
        if not isinstance(value, str) or value not in allowed:
            raise ValueError(f"Invalid {name}. Choose from: {', '.join(sorted(allowed))}.")
        if value != "auto":
            args[name] = value

    if args.get("background") == "transparent" and args.get("output_format") == "jpeg":
        raise ValueError("Invalid output_format. Transparent background requires png or webp.")

    for name, default, minimum, maximum in (
        ("n", 1, 1, 10),
        ("output_compression", None, 0, 100),
    ):
        value = parameters.get(name, default)
        if name == "output_compression" and value in (None, ""):
            continue
        error = f"Invalid {name}. Choose an integer between {minimum} and {maximum}."
        try:
            number = int(value)
        except (TypeError, ValueError, OverflowError) as e:
            raise ValueError(error) from e
        if (
            isinstance(value, bool)
            or (not isinstance(value, str) and value != number)
            or not minimum <= number <= maximum
        ):
            raise ValueError(error)
        if name == "n" or args.get("output_format") in {"jpeg", "webp"}:
            args[name] = number

    return args


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


def build_usage_output(
    response: Any, model: str, operation: str, image_count: int
) -> dict[str, Any] | None:
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

import base64
import re
from typing import Any

from openai.types import ImagesResponse


def build_image_args(
    parameters: dict[str, Any], *, edit: bool = False
) -> dict[str, Any]:
    model = parameters.get("model", "gpt-image-2")
    if not isinstance(model, str) or model not in {
        "gpt-image-2",
        "gpt-image-2.5-flare",
        "gpt-image-2.5-sunburst",
        "gpt-image-2.6-flare",
        "gpt-image-2.6-sunburst",
    }:
        raise ValueError("Invalid model. Select a GPT Image model from the list.")

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
    formats = {"auto", "png", "jpeg", "webp"}
    if model.startswith("gpt-image-2.6-"):
        formats.add("gif")
        if not edit:
            formats.add("svg")
    complexity = parameters.get("complexity", "auto")
    if complexity != "auto":
        if not model.startswith("gpt-image-2.6-") or complexity not in (
            "low",
            "medium",
            "high",
        ):
            raise ValueError(
                "Invalid complexity. GPT Image 2.6 supports low, medium, and high."
            )
        args["complexity"] = complexity

    for name, allowed in (
        ("quality", qualities),
        ("background", {"auto", "opaque", "transparent"}),
        ("output_format", formats),
    ):
        value = parameters.get(name, "auto")
        if not isinstance(value, str) or value not in allowed:
            raise ValueError(f"Invalid {name}. Choose from: {', '.join(sorted(allowed))}.")
        if value != "auto":
            args[name] = value

    if args.get("background") == "transparent" and args.get("output_format") in {
        "jpeg",
        "gif",
        "svg",
    }:
        raise ValueError("Invalid output_format. Transparent background requires png or webp.")

    for name, default, minimum, maximum in (
        ("n", 1, 1, 10),
        ("output_compression", None, 0, 100),
        ("frame_count", None, 2, 16),
        ("frame_duration_ms", None, 20, 2000),
    ):
        value = parameters.get(name, default)
        if default is None and value in (None, ""):
            continue
        if (
            name in ("frame_count", "frame_duration_ms")
            and args.get("output_format") != "gif"
        ):
            raise ValueError(f"{name} requires GIF output.")
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
        if name != "output_compression" or args.get("output_format") in {
            "jpeg",
            "webp",
        }:
            args[name] = number

    if args.get("output_format") == "svg" and args["n"] != 1:
        raise ValueError("SVG output requires n=1.")
    author_model = parameters.get("svg_author_model")
    if author_model not in (None, ""):
        if args.get("output_format") != "svg":
            raise ValueError("svg_author_model requires SVG output.")
        if not isinstance(author_model, str) or not author_model.strip():
            raise ValueError("Enter a model ID for svg_author_model.")
        args["svg"] = {"model": author_model.strip()}
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


def build_usage_outputs(
    response: ImagesResponse, model: str, operation: str, image_count: int
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    usage = response.model_dump(mode="json", include={"usage", "svg_usage"}, exclude_none=True)
    if not usage:
        return {}, None
    metadata = usage.copy()
    if "usage" in metadata:
        metadata["token_usage"] = metadata.pop("usage")
    result = {"model": model, "operation": operation, "image_count": image_count, **usage}
    return metadata, {"data": [result]}

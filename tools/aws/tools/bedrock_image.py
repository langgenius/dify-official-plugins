"""Generate images via Amazon Bedrock Stability image models."""

from __future__ import annotations

import base64
import json
import logging
import math
import uuid
from collections.abc import Generator
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

logger = logging.getLogger(__name__)

MODEL_SD35 = "stability.sd3-5-large-v1:0"
MODEL_CORE = "stability.stable-image-core-v1:1"
MODEL_ULTRA = "stability.stable-image-ultra-v1:1"

SUPPORTED_MODELS = frozenset({MODEL_SD35, MODEL_CORE, MODEL_ULTRA})
ASPECT_RATIOS = frozenset(
    {"16:9", "1:1", "21:9", "2:3", "3:2", "4:5", "5:4", "9:16", "9:21"}
)
ALLOWED_INPUT_MIMES = frozenset({"image/jpeg", "image/jpg", "image/png", "image/webp"})
OUTPUT_FORMATS_SD35 = frozenset({"jpeg", "png", "webp"})
OUTPUT_FORMATS_CORE_ULTRA = frozenset({"jpeg", "png"})

PROMPT_MAX_CHARS = 10000
SEED_MAX_SD35 = 4294967294
SEED_MAX_CORE_ULTRA = 4294967295
MAX_INPUT_IMAGE_BYTES = 10 * 1024 * 1024
DEFAULT_STRENGTH = 0.5
DEFAULT_REGION = "us-west-2"
DEFAULT_MODEL = MODEL_SD35
DEFAULT_OUTPUT_FORMAT = "png"
DEFAULT_ASPECT_RATIO = "1:1"

MIME_BY_FORMAT = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
}


def _format_debug_message(title: str, fields: dict[str, Any]) -> str:
    lines = [title]
    for key, value in fields.items():
        if value is None:
            continue
        lines.append(f"{key}={value}")
    return "\n".join(lines)


def _client_error_hint(error_code: str) -> str:
    hints = {
        "AccessDeniedException": (
            "Model access may be disabled in this region, or the IAM principal "
            "lacks bedrock:InvokeModel."
        ),
        "ValidationException": "Check the AWS error message for the invalid field.",
        "ResourceNotFoundException": (
            "This model is not available in the configured region. "
            "AWS examples use us-west-2."
        ),
        "ThrottlingException": "Rate limited. Retry after a short delay.",
        "ExpiredTokenException": (
            "Credentials expired. Refresh SSO/STS credentials. "
            "Temporary credentials require aws_session_token."
        ),
        "UnrecognizedClientException": (
            "Credentials are missing or invalid. "
            "Temporary credentials require aws_session_token."
        ),
    }
    return hints.get(error_code, "See the AWS error message and request_id.")


def _no_image_hint(finish_reasons: list[Any]) -> str:
    reasons = [str(reason) for reason in finish_reasons if reason is not None]
    if any(reason.startswith("Filter reason:") for reason in reasons):
        return (
            "The safety filter rejected this request. "
            "Revise the prompt or input image and retry. "
            "Use request_id with CloudWatch model invocation logs "
            "if logging is enabled."
        )
    if any(reason == "Inference error" for reason in reasons):
        return (
            "The model reported an inference error without returning an image. "
            "Retry the request. Use request_id with CloudWatch model invocation "
            "logs if logging is enabled."
        )
    return (
        "Bedrock did not return an image. Check finish_reasons and request_id. "
        "Use CloudWatch model invocation logs if logging is enabled."
    )


def _normalize_images(images: Any) -> list[Any]:
    if images is None or images == "":
        return []
    if not isinstance(images, list):
        images = [images]
    return [image for image in images if image is not None and image != ""]


def _parse_int_param(value: Any, *, field: str, default: int = 0) -> int | str:
    """Parse an integer parameter without silently truncating floats/bools."""
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return _format_debug_message(
            "Invalid parameter.",
            {
                "field": field,
                "value": value,
                "allowed": "integer (booleans are not accepted)",
            },
        )
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            return _format_debug_message(
                "Invalid parameter.",
                {
                    "field": field,
                    "value": value,
                    "allowed": "integer (fractional values are not accepted)",
                },
            )
        try:
            return int(value)
        except OverflowError:
            return _format_debug_message(
                "Invalid parameter.",
                {
                    "field": field,
                    "value": value,
                    "allowed": "integer within finite range",
                },
            )
    try:
        text = str(value).strip()
        parsed = float(text)
        if not math.isfinite(parsed) or not parsed.is_integer():
            return _format_debug_message(
                "Invalid parameter.",
                {
                    "field": field,
                    "value": value,
                    "allowed": "integer",
                },
            )
        return int(parsed)
    except (TypeError, ValueError, OverflowError):
        return _format_debug_message(
            "Invalid parameter.",
            {
                "field": field,
                "value": value,
                "allowed": "integer",
            },
        )


def _file_attr(file_obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(file_obj, dict):
        return file_obj.get(name, default)
    return getattr(file_obj, name, default)


class BedrockImageTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        validation = self._validate_and_extract(tool_parameters)
        if isinstance(validation, str):
            yield self.create_text_message(validation)
            return

        params = validation
        model = params["model"]
        region = params["aws_region"]
        mode = params["mode"]
        prompt_chars = len(params["prompt"])
        input_image_desc = params["input_image_desc"]

        try:
            client_kwargs = self._build_client_kwargs(params)
            bedrock = boto3.Session().client("bedrock-runtime", **client_kwargs)
        except NoCredentialsError as exc:
            message = _format_debug_message(
                "AWS credentials are missing.",
                {
                    "model": model,
                    "region": region,
                    "mode": mode,
                    "error": f"{type(exc).__name__}: {exc}",
                    "hint": _client_error_hint("UnrecognizedClientException"),
                },
            )
            logger.exception(message)
            yield self.create_text_message(message)
            return
        except Exception as exc:
            message = _format_debug_message(
                "Failed to initialize Bedrock client.",
                {
                    "model": model,
                    "region": region,
                    "mode": mode,
                    "error": f"{type(exc).__name__}: {exc}",
                    "hint": "Check aws_region and credential parameters.",
                },
            )
            logger.exception(message)
            yield self.create_text_message(message)
            return

        body = self._build_request_body(params)
        request_id = "unknown"

        try:
            response = bedrock.invoke_model(
                modelId=model,
                body=json.dumps(body),
                accept="application/json",
                contentType="application/json",
            )
            request_id = (
                response.get("ResponseMetadata", {}).get("RequestId") or "unknown"
            )
            response_body = json.loads(response["body"].read())
        except ClientError as exc:
            error = exc.response.get("Error", {})
            error_code = error.get("Code", "Unknown")
            error_message = error.get("Message", str(exc))
            meta = exc.response.get("ResponseMetadata", {})
            request_id = meta.get("RequestId") or "unknown"
            http_status = meta.get("HTTPStatusCode")
            message = _format_debug_message(
                "AWS service error.",
                {
                    "error_code": error_code,
                    "message": error_message,
                    "model": model,
                    "region": region,
                    "mode": mode,
                    "request_id": request_id,
                    "http_status": http_status,
                    "prompt_chars": prompt_chars,
                    "input_image": input_image_desc,
                    "hint": _client_error_hint(error_code),
                },
            )
            logger.error(message)
            yield self.create_text_message(message)
            return
        except Exception as exc:
            message = _format_debug_message(
                "Failed to invoke Bedrock image model.",
                {
                    "model": model,
                    "region": region,
                    "mode": mode,
                    "request_id": request_id,
                    "prompt_chars": prompt_chars,
                    "input_image": input_image_desc,
                    "error": f"{type(exc).__name__}: {exc}",
                    "hint": "See the exception message and request_id.",
                },
            )
            logger.exception(message)
            yield self.create_text_message(message)
            return

        finish_reasons = response_body.get("finish_reasons") or []
        images = response_body.get("images") or []
        blocking_reasons = [reason for reason in finish_reasons if reason is not None]
        if blocking_reasons or not images:
            reason_text = ",".join(str(r) for r in finish_reasons) if finish_reasons else "none"
            message = _format_debug_message(
                "Bedrock returned no image.",
                {
                    "finish_reasons": reason_text,
                    "model": model,
                    "region": region,
                    "mode": mode,
                    "request_id": request_id,
                    "prompt_chars": prompt_chars,
                    "input_image": input_image_desc,
                    "hint": _no_image_hint(finish_reasons),
                },
            )
            logger.warning(message)
            yield self.create_text_message(message)
            return

        output_format = params["output_format"]
        image_bytes = base64.b64decode(images[0])
        seeds = response_body.get("seeds") or []
        response_seed = seeds[0] if seeds else "unknown"
        strength_sent = params.get("strength_sent")

        s3_status = "not-uploaded"
        s3_uri = params.get("image_output_s3uri")
        if s3_uri:
            try:
                uploaded_uri = self._upload_to_s3(
                    image_bytes=image_bytes,
                    s3_uri=s3_uri,
                    region=region,
                    output_format=output_format,
                    client_kwargs=client_kwargs,
                )
                s3_status = uploaded_uri
            except Exception as exc:
                s3_error = _format_debug_message(
                    "Image was generated but S3 upload failed.",
                    {
                        "model": model,
                        "region": region,
                        "request_id": request_id,
                        "s3_uri": s3_uri,
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                )
                logger.exception(s3_error)
                yield self.create_text_message(s3_error)
                s3_status = f"upload-failed:{s3_uri}"

        success = _format_debug_message(
            "Image generated.",
            {
                "model": model,
                "region": region,
                "mode": mode,
                "request_id": request_id,
                "seed": response_seed,
                "format": output_format,
                "strength": strength_sent if strength_sent is not None else "omitted",
                "s3": s3_status,
            },
        )
        logger.info(success)
        yield self.create_text_message(success)
        yield self.create_blob_message(
            blob=image_bytes,
            meta={
                "filename": f"bedrock-image.{output_format}",
                "mime_type": MIME_BY_FORMAT[output_format],
            },
        )

    def _validate_and_extract(
        self, tool_parameters: dict[str, Any]
    ) -> dict[str, Any] | str:
        prompt = (tool_parameters.get("prompt") or "").strip()
        if not prompt:
            return _format_debug_message(
                "Invalid parameter.",
                {
                    "field": "prompt",
                    "value": "(empty)",
                    "allowed": "non-empty string, max 10000 characters",
                },
            )
        if len(prompt) > PROMPT_MAX_CHARS:
            return _format_debug_message(
                "Invalid parameter.",
                {
                    "field": "prompt",
                    "value": f"length={len(prompt)}",
                    "allowed": f"1..{PROMPT_MAX_CHARS} characters",
                },
            )

        model = tool_parameters.get("model") or DEFAULT_MODEL
        if model not in SUPPORTED_MODELS:
            return _format_debug_message(
                "Invalid parameter.",
                {
                    "field": "model",
                    "value": model,
                    "allowed": ",".join(sorted(SUPPORTED_MODELS)),
                },
            )

        aws_region = (tool_parameters.get("aws_region") or DEFAULT_REGION).strip()
        if not aws_region:
            return _format_debug_message(
                "Invalid parameter.",
                {
                    "field": "aws_region",
                    "value": "(empty)",
                    "allowed": "non-empty AWS region, e.g. us-west-2",
                },
            )

        access_key = tool_parameters.get("aws_access_key_id") or None
        secret_key = tool_parameters.get("aws_secret_access_key") or None
        session_token = tool_parameters.get("aws_session_token") or None
        if bool(access_key) != bool(secret_key):
            return _format_debug_message(
                "Invalid parameter.",
                {
                    "field": "aws_access_key_id/aws_secret_access_key",
                    "value": (
                        f"access_key_set={bool(access_key)},"
                        f"secret_key_set={bool(secret_key)}"
                    ),
                    "allowed": "provide both keys, or leave both empty for the default credential chain",
                },
            )
        if session_token and not (access_key and secret_key):
            return _format_debug_message(
                "Invalid parameter.",
                {
                    "field": "aws_session_token",
                    "value": "session_token_set=True without access/secret keys",
                    "allowed": (
                        "temporary credentials require aws_access_key_id, "
                        "aws_secret_access_key, and aws_session_token together"
                    ),
                },
            )

        output_format = (
            tool_parameters.get("output_format") or DEFAULT_OUTPUT_FORMAT
        ).lower()
        allowed_formats = (
            OUTPUT_FORMATS_SD35 if model == MODEL_SD35 else OUTPUT_FORMATS_CORE_ULTRA
        )
        if output_format not in allowed_formats:
            return _format_debug_message(
                "Invalid parameter.",
                {
                    "field": "output_format",
                    "value": output_format,
                    "model": model,
                    "allowed": ",".join(sorted(allowed_formats)),
                },
            )

        aspect_ratio = tool_parameters.get("aspect_ratio") or DEFAULT_ASPECT_RATIO
        if aspect_ratio not in ASPECT_RATIOS:
            return _format_debug_message(
                "Invalid parameter.",
                {
                    "field": "aspect_ratio",
                    "value": aspect_ratio,
                    "allowed": ",".join(sorted(ASPECT_RATIOS)),
                },
            )

        seed = _parse_int_param(tool_parameters.get("seed", 0), field="seed", default=0)
        if isinstance(seed, str):
            return seed
        seed_max = SEED_MAX_SD35 if model == MODEL_SD35 else SEED_MAX_CORE_ULTRA
        if seed < 0 or seed > seed_max:
            return _format_debug_message(
                "Invalid parameter.",
                {
                    "field": "seed",
                    "value": seed,
                    "model": model,
                    "allowed": f"0..{seed_max}",
                },
            )

        images = _normalize_images(tool_parameters.get("images"))
        if len(images) > 1:
            return _format_debug_message(
                "Invalid parameter.",
                {
                    "field": "images",
                    "value": f"count={len(images)}",
                    "allowed": "0 or 1 image file",
                },
            )

        input_image_b64: Optional[str] = None
        input_image_desc = "none"
        if images:
            if model == MODEL_CORE:
                return _format_debug_message(
                    "Invalid parameter.",
                    {
                        "field": "images",
                        "value": "reference image provided",
                        "model": MODEL_CORE,
                        "allowed": (
                            "Stable Image Core supports text-to-image only. "
                            f"Use {MODEL_SD35} or {MODEL_ULTRA} for image-to-image."
                        ),
                    },
                )

            image_file = images[0]
            mime_type = (_file_attr(image_file, "mime_type") or "").lower()
            if mime_type == "image/jpg":
                mime_type = "image/jpeg"
            if mime_type not in ALLOWED_INPUT_MIMES:
                return _format_debug_message(
                    "Invalid parameter.",
                    {
                        "field": "images.mime_type",
                        "value": mime_type or "(missing)",
                        "allowed": "image/jpeg,image/png,image/webp",
                    },
                )
            blob = _file_attr(image_file, "blob")
            if blob is None:
                return _format_debug_message(
                    "Invalid parameter.",
                    {
                        "field": "images.blob",
                        "value": "(missing)",
                        "allowed": "binary image content from a Dify file variable",
                    },
                )
            if isinstance(blob, memoryview):
                blob = blob.tobytes()
            if not isinstance(blob, (bytes, bytearray)):
                return _format_debug_message(
                    "Invalid parameter.",
                    {
                        "field": "images.blob",
                        "value": type(blob).__name__,
                        "allowed": "bytes",
                    },
                )
            blob = bytes(blob)
            if len(blob) > MAX_INPUT_IMAGE_BYTES:
                return _format_debug_message(
                    "Invalid parameter.",
                    {
                        "field": "images.blob",
                        "value": f"size={len(blob)}B",
                        "allowed": f"<= {MAX_INPUT_IMAGE_BYTES}B",
                    },
                )
            input_image_b64 = base64.b64encode(blob).decode("utf-8")
            input_image_desc = f"{mime_type};{len(blob)}B"

        strength_sent: Optional[float] = None
        if input_image_b64 is not None:
            strength_raw = tool_parameters.get("strength", DEFAULT_STRENGTH)
            try:
                strength = (
                    float(strength_raw)
                    if strength_raw is not None and strength_raw != ""
                    else DEFAULT_STRENGTH
                )
            except (TypeError, ValueError):
                return _format_debug_message(
                    "Invalid parameter.",
                    {
                        "field": "strength",
                        "value": strength_raw,
                        "allowed": "number in 0..1 (lower keeps more of the input image)",
                    },
                )
            if strength < 0.0 or strength > 1.0:
                return _format_debug_message(
                    "Invalid parameter.",
                    {
                        "field": "strength",
                        "value": strength,
                        "allowed": "0.0..1.0 (lower keeps more of the input image)",
                    },
                )
            strength_sent = strength

        s3_uri = (tool_parameters.get("image_output_s3uri") or "").strip()
        if s3_uri:
            parsed_s3 = urlparse(s3_uri)
            if parsed_s3.scheme != "s3" or not parsed_s3.netloc:
                return _format_debug_message(
                    "Invalid parameter.",
                    {
                        "field": "image_output_s3uri",
                        "value": s3_uri,
                        "allowed": "s3://bucket/prefix or empty",
                    },
                )

        negative_prompt = (tool_parameters.get("negative_prompt") or "").strip()
        if len(negative_prompt) > PROMPT_MAX_CHARS:
            return _format_debug_message(
                "Invalid parameter.",
                {
                    "field": "negative_prompt",
                    "value": f"length={len(negative_prompt)}",
                    "allowed": f"0..{PROMPT_MAX_CHARS} characters",
                },
            )

        mode = "image-to-image" if input_image_b64 is not None else "text-to-image"
        return {
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "model": model,
            "aws_region": aws_region,
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
            "aws_session_token": session_token,
            "output_format": output_format,
            "aspect_ratio": aspect_ratio,
            "seed": seed,
            "input_image_b64": input_image_b64,
            "input_image_desc": input_image_desc,
            "strength_sent": strength_sent,
            "image_output_s3uri": s3_uri or None,
            "mode": mode,
        }

    def _build_client_kwargs(self, params: dict[str, Any]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"region_name": params["aws_region"]}
        if params.get("aws_access_key_id") and params.get("aws_secret_access_key"):
            kwargs["aws_access_key_id"] = params["aws_access_key_id"]
            kwargs["aws_secret_access_key"] = params["aws_secret_access_key"]
            if params.get("aws_session_token"):
                kwargs["aws_session_token"] = params["aws_session_token"]
        return kwargs

    def _build_request_body(self, params: dict[str, Any]) -> dict[str, Any]:
        model = params["model"]
        body: dict[str, Any] = {
            "prompt": params["prompt"],
            "seed": params["seed"],
            "output_format": params["output_format"],
        }
        if params["negative_prompt"]:
            body["negative_prompt"] = params["negative_prompt"]

        if params["input_image_b64"] is None:
            body["aspect_ratio"] = params["aspect_ratio"]
            # Core docs omit mode; SD 3.5 / Ultra text-to-image accept it.
            if model in {MODEL_SD35, MODEL_ULTRA}:
                body["mode"] = "text-to-image"
            return body

        # Image-to-image: Core already rejected in validation.
        body["image"] = params["input_image_b64"]
        body["strength"] = params["strength_sent"]
        if model == MODEL_SD35:
            body["mode"] = "image-to-image"
        # Ultra: send image + strength only; do not send mode=image-to-image.
        return body

    def _upload_to_s3(
        self,
        *,
        image_bytes: bytes,
        s3_uri: str,
        region: str,
        output_format: str,
        client_kwargs: dict[str, Any],
    ) -> str:
        parsed = urlparse(s3_uri)
        bucket = parsed.netloc
        base_path = parsed.path.lstrip("/")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        unique = uuid.uuid4().hex[:8]
        filename = f"bedrock-image-{timestamp}-{unique}.{output_format}"
        key = f"{base_path.rstrip('/')}/{filename}" if base_path else filename

        s3_kwargs = dict(client_kwargs)
        s3_kwargs["region_name"] = region
        s3_client = boto3.Session().client("s3", **s3_kwargs)
        s3_client.put_object(
            Bucket=bucket,
            Key=key,
            Body=image_bytes,
            ContentType=MIME_BY_FORMAT[output_format],
        )
        return f"s3://{bucket}/{key}"

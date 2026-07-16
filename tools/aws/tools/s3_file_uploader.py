"""
Location: tools/s3_file_uploader.py
Purpose:  Upload a file received from a prior Dify workflow node to a specified S3 bucket.

This tool consumes the binary asset produced by an upstream node (e.g. Start file input,
LLM with file output, or another tool) and persists it to Amazon S3 so that downstream
nodes can reference it by S3 URI or via an optional presigned URL.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

# ---------------------------------------------------------------------------
# Inline credential helpers (kept self-contained on purpose so this tool does
# not rely on a shared utils/ module that the rest of this repo does not use).
# ---------------------------------------------------------------------------


def _resolve_aws_credentials(
    tool: Any, tool_parameters: dict[str, Any]
) -> dict[str, Optional[str]]:
    """Merge provider-level credentials with per-invocation tool parameters.

    Tool-parameter values win over provider credentials so callers can override
    a default profile per invocation. ``aws_session_token`` is intentionally
    only sourced from tool parameters because the provider schema does not
    expose it (STS-issued temporary credentials are passed inline).
    """
    runtime_credentials = getattr(getattr(tool, "runtime", None), "credentials", {}) or {}

    aws_access_key_id = tool_parameters.get("aws_access_key_id") or runtime_credentials.get(
        "aws_access_key_id"
    )
    aws_secret_access_key = tool_parameters.get("aws_secret_access_key") or runtime_credentials.get(
        "aws_secret_access_key"
    )
    aws_session_token = tool_parameters.get("aws_session_token")
    aws_region = (
        tool_parameters.get("aws_region") or runtime_credentials.get("aws_region") or "us-east-1"
    )

    return {
        "aws_access_key_id": aws_access_key_id,
        "aws_secret_access_key": aws_secret_access_key,
        "aws_session_token": aws_session_token,
        "aws_region": aws_region,
    }


def _build_boto3_client_kwargs(credentials: dict[str, Optional[str]]) -> dict[str, Any]:
    """Translate the credential bundle into kwargs accepted by ``boto3.client``."""
    kwargs: dict[str, Any] = {}
    if credentials.get("aws_region"):
        kwargs["region_name"] = credentials["aws_region"]
    if credentials.get("aws_access_key_id") and credentials.get("aws_secret_access_key"):
        kwargs["aws_access_key_id"] = credentials["aws_access_key_id"]
        kwargs["aws_secret_access_key"] = credentials["aws_secret_access_key"]
        if credentials.get("aws_session_token"):
            kwargs["aws_session_token"] = credentials["aws_session_token"]
    return kwargs


def _parse_presign_expiry(value: Any, default: int = 3600) -> int:
    """Safely coerce the ``presign_expiry`` parameter to int.

    Tolerates ``None``, empty string, and stringified numbers that the Dify UI
    can pass for an empty optional ``number`` field. Falls back to ``default``
    on any parsing failure rather than crashing the workflow with TypeError /
    ValueError.
    """
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Tool implementation
# ---------------------------------------------------------------------------


def _sanitize_prefix(prefix: Optional[str]) -> str:
    """Trim leading/trailing slashes from a prefix and tolerate empty input."""
    if not prefix:
        return ""
    return prefix.strip("/ ")


class S3FileUploader(Tool):
    """Upload a Dify file variable to S3.

    The boto3 client is created as a local variable inside ``_invoke`` (instead
    of cached on ``self``) to keep this tool safe across concurrent workflow
    executions: tool instances may be reused by the plugin runtime, and a
    cached client tied to one tenant's credentials must never leak into
    another invocation.
    """

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Read the input file and upload it to S3, returning the resulting URI as JSON."""
        try:
            credentials = _resolve_aws_credentials(self, tool_parameters)
            client_kwargs = _build_boto3_client_kwargs(credentials)
            s3_client = boto3.client("s3", **client_kwargs)
        except Exception as exc:  # pragma: no cover - boto3 init errors
            yield self.create_text_message(f"Failed to initialize AWS client: {exc}")
            return

        input_file = tool_parameters.get("input_file")
        if not input_file:
            yield self.create_text_message("input_file parameter is required")
            return

        try:
            file_bytes: bytes = input_file.blob  # type: ignore[attr-defined]
        except Exception as exc:
            yield self.create_text_message(f"Failed to read input_file: {exc}")
            return

        bucket_name = tool_parameters.get("bucket_name")
        if not bucket_name:
            yield self.create_text_message("bucket_name parameter is required")
            return

        key_prefix = _sanitize_prefix(tool_parameters.get("key_prefix"))
        requested_key = tool_parameters.get("object_key") or getattr(input_file, "filename", None)
        fallback_key = (
            getattr(input_file, "url", "").rstrip("/").split("/")[-1]
            if getattr(input_file, "url", None)
            else None
        )
        object_key = requested_key or fallback_key or f"dify-upload-{uuid.uuid4().hex}"
        object_key = object_key.lstrip("/")
        if key_prefix:
            object_key = f"{key_prefix}/{object_key}"

        content_type = getattr(input_file, "mime_type", None) or "application/octet-stream"

        try:
            s3_client.put_object(
                Bucket=bucket_name,
                Key=object_key,
                Body=file_bytes,
                ContentType=content_type,
            )
        except ClientError as exc:
            error_message = exc.response.get("Error", {}).get("Message", str(exc))
            yield self.create_text_message(f"Failed to upload file to S3: {error_message}")
            return

        s3_uri = f"s3://{bucket_name}/{object_key}"
        result_payload: dict[str, Any] = {
            "bucket_name": bucket_name,
            "object_key": object_key,
            "s3_uri": s3_uri,
        }

        text_message = None
        if tool_parameters.get("generate_presign_url"):
            expiry_seconds = _parse_presign_expiry(tool_parameters.get("presign_expiry"))
            try:
                presigned_url = s3_client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": bucket_name, "Key": object_key},
                    ExpiresIn=expiry_seconds,
                )
                result_payload["presigned_url"] = presigned_url
                result_payload["presign_expiry"] = expiry_seconds
                text_message = self.create_text_message(presigned_url)
            except ClientError as exc:
                error_message = exc.response.get("Error", {}).get("Message", str(exc))
                yield self.create_text_message(
                    f"Upload succeeded but failed to create presigned URL: {error_message}"
                )
                return
        else:
            text_message = self.create_text_message(s3_uri)

        yield self.create_json_message(result_payload)
        if text_message:
            yield text_message

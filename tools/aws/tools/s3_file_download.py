"""
Location: tools/s3_file_download.py
Purpose:  Download an S3 object as a Dify file variable for downstream workflow nodes.

This tool complements ``s3_file_uploader``. It accepts an ``s3://bucket/key`` URI,
fetches the object via boto3, and emits the binary as a Dify file plus metadata as
both JSON and a key=value text block, so downstream nodes can treat it as a file
input or read individual fields like ``content_length`` / ``etag``.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any, Optional
from urllib.parse import urlparse

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
    kwargs: dict[str, Any] = {}
    if credentials.get("aws_region"):
        kwargs["region_name"] = credentials["aws_region"]
    if credentials.get("aws_access_key_id") and credentials.get("aws_secret_access_key"):
        kwargs["aws_access_key_id"] = credentials["aws_access_key_id"]
        kwargs["aws_secret_access_key"] = credentials["aws_secret_access_key"]
        if credentials.get("aws_session_token"):
            kwargs["aws_session_token"] = credentials["aws_session_token"]
    return kwargs


# ---------------------------------------------------------------------------
# Tool implementation
# ---------------------------------------------------------------------------


def _build_metadata_text(metadata: dict[str, Any]) -> str:
    """Render a simple ``key: value`` block for human-readable downstream display."""
    lines = []
    for key, value in metadata.items():
        if value is None:
            continue
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


class S3FileDownload(Tool):
    """Download an S3 object as a Dify file variable.

    The boto3 client is created as a local variable inside ``_invoke`` (instead
    of cached on ``self``) to keep this tool safe across concurrent workflow
    executions: tool instances may be reused by the plugin runtime, and a
    cached client tied to one tenant's credentials must never leak into
    another invocation.
    """

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Download an S3 object and emit it as a Dify file plus metadata."""
        try:
            credentials = _resolve_aws_credentials(self, tool_parameters)
            client_kwargs = _build_boto3_client_kwargs(credentials)
            s3_client = boto3.client("s3", **client_kwargs)
        except Exception as exc:  # pragma: no cover - boto3 init errors
            yield self.create_text_message(f"Failed to initialize AWS client: {exc}")
            return

        s3_uri = tool_parameters.get("s3_uri")
        if not s3_uri:
            yield self.create_text_message("s3_uri parameter is required")
            return

        parsed_uri = urlparse(s3_uri)
        if parsed_uri.scheme != "s3" or not parsed_uri.netloc or not parsed_uri.path:
            yield self.create_text_message("Invalid S3 URI format. Use s3://bucket/key")
            return

        bucket = parsed_uri.netloc
        key = parsed_uri.path.lstrip("/")

        try:
            response = s3_client.get_object(Bucket=bucket, Key=key)
            file_bytes = response["Body"].read()
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code == "NoSuchBucket":
                yield self.create_text_message(f"Bucket '{bucket}' does not exist")
                return
            if error_code == "NoSuchKey":
                yield self.create_text_message(
                    f"Object '{key}' does not exist in bucket '{bucket}'"
                )
                return
            error_message = exc.response.get("Error", {}).get("Message", str(exc))
            yield self.create_text_message(f"Failed to download S3 object: {error_message}")
            return
        except Exception as exc:
            yield self.create_text_message(f"Failed to download S3 object: {exc}")
            return

        # Tolerate trailing slashes in the key (e.g. s3://bucket/path/) so the
        # filename never ends up empty.
        filename = key.rstrip("/").split("/")[-1] if key else "downloaded_file"
        if not filename:
            filename = "downloaded_file"
        content_type = response.get("ContentType") or "application/octet-stream"
        metadata_dict = {
            "bucket": bucket,
            "key": key,
            "content_type": content_type,
            "content_length": response.get("ContentLength"),
            "etag": response.get("ETag"),
            "last_modified": (
                response.get("LastModified").isoformat() if response.get("LastModified") else None
            ),
            "s3_uri": s3_uri,
        }
        metadata_text = _build_metadata_text(metadata_dict)

        blob_meta = {
            "filename": filename,
            "mime_type": content_type,
            "s3_uri": s3_uri,
        }
        yield self.create_blob_message(file_bytes, meta=blob_meta)
        yield self.create_json_message(metadata_dict)
        yield self.create_text_message(metadata_text or f"bucket: {bucket}\nkey: {key}")

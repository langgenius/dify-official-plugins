"""
Location: tools/s3_files_download.py
Purpose:  Batch-download multiple S3 objects as Dify file variables for downstream
          workflow nodes.

This tool is the array-input counterpart of ``s3_file_download``. It accepts a list
of ``s3://bucket/key`` URIs (``s3_uris: array[string]``), fetches each object via
boto3, and emits one Dify file per successful download in the same order as the
input list, plus aggregated metadata as JSON and a per-line text summary.

Per-URI failures do NOT abort the batch: each URI's outcome is captured in the
``results`` list with ``status = "ok" | "failed"``. The whole invocation only
emits a top-level error when **every** URI fails.
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
# Mirrors the helpers in the single-URI s3_file_download for consistency.
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


def _normalize_s3_uris(raw: Any) -> list[str]:
    """Coerce ``s3_uris`` into a flat list of strings.

    Dify passes ``array[string]`` parameters as a Python list, but be defensive
    against a single string slipping through. Whitespace-only entries are
    silently dropped.
    """
    if raw is None:
        return []
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, list):
        items = [str(item) for item in raw if item is not None]
    else:
        items = [str(raw)]
    return [item.strip() for item in items if item and item.strip()]


def _validate_s3_uri(uri: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Parse and validate an s3:// URI.

    Returns ``(bucket, key, error_message)``. On success the error is ``None``.
    On failure the bucket/key are ``None`` and the error string explains why.
    """
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path:
        return None, None, "Invalid S3 URI format. Use s3://bucket/key"
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    if not key:
        return None, None, "Invalid S3 URI: missing object key"
    return bucket, key, None


def _build_metadata_text(metadata: dict[str, Any]) -> str:
    """Render a simple ``key: value`` block for a single result entry."""
    lines = []
    for key, value in metadata.items():
        if value is None:
            continue
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tool implementation
# ---------------------------------------------------------------------------


class S3FilesDownload(Tool):
    """Batch-download multiple S3 objects as Dify file variables.

    The boto3 client is created once per ``_invoke`` call (not cached on
    ``self``) for the same per-tenant safety reason as ``s3_file_download``.
    Within a single invocation the client is reused across all URIs, which is
    safe because all entries share the same credential bundle.
    """

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Download every input URI and emit aggregated files + metadata."""
        try:
            credentials = _resolve_aws_credentials(self, tool_parameters)
            client_kwargs = _build_boto3_client_kwargs(credentials)
            s3_client = boto3.client("s3", **client_kwargs)
        except Exception as exc:  # pragma: no cover - boto3 init errors
            yield self.create_text_message(f"Failed to initialize AWS client: {exc}")
            return

        s3_uris = _normalize_s3_uris(tool_parameters.get("s3_uris"))
        if not s3_uris:
            yield self.create_text_message("s3_uris parameter is required and must not be empty")
            return

        results: list[dict[str, Any]] = []
        # Collect blob payloads to yield AFTER the json/text messages so that
        # downstream nodes inspecting `files` see the full list at once. We
        # still preserve input order.
        blobs_to_yield: list[tuple[bytes, dict[str, Any]]] = []

        for index, s3_uri in enumerate(s3_uris):
            entry: dict[str, Any] = {"index": index, "s3_uri": s3_uri}

            bucket, key, validation_error = _validate_s3_uri(s3_uri)
            if validation_error:
                entry["status"] = "failed"
                entry["error"] = validation_error
                results.append(entry)
                continue

            entry["bucket"] = bucket
            entry["key"] = key

            try:
                response = s3_client.get_object(Bucket=bucket, Key=key)
                file_bytes = response["Body"].read()
            except ClientError as exc:
                error_code = exc.response.get("Error", {}).get("Code")
                if error_code == "NoSuchBucket":
                    entry["error"] = f"Bucket '{bucket}' does not exist"
                elif error_code == "NoSuchKey":
                    entry["error"] = f"Object '{key}' does not exist in bucket '{bucket}'"
                else:
                    entry["error"] = exc.response.get("Error", {}).get("Message", str(exc))
                entry["status"] = "failed"
                results.append(entry)
                continue
            except Exception as exc:
                entry["status"] = "failed"
                entry["error"] = f"Failed to download S3 object: {exc}"
                results.append(entry)
                continue

            filename = key.rstrip("/").split("/")[-1] if key else "downloaded_file"
            if not filename:
                filename = "downloaded_file"
            content_type = response.get("ContentType") or "application/octet-stream"
            entry["status"] = "ok"
            entry["content_type"] = content_type
            entry["content_length"] = response.get("ContentLength")
            entry["etag"] = response.get("ETag")
            entry["last_modified"] = (
                response.get("LastModified").isoformat() if response.get("LastModified") else None
            )
            entry["filename"] = filename

            blob_meta = {
                "filename": filename,
                "mime_type": content_type,
                "s3_uri": s3_uri,
            }
            blobs_to_yield.append((file_bytes, blob_meta))
            results.append(entry)

        ok_count = sum(1 for r in results if r.get("status") == "ok")
        failed_count = len(results) - ok_count

        json_payload = {
            "count": len(results),
            "ok": ok_count,
            "failed": failed_count,
            "results": results,
        }

        text_lines: list[str] = []
        for entry in results:
            if entry.get("status") == "ok":
                summary = _build_metadata_text(
                    {
                        "bucket": entry.get("bucket"),
                        "key": entry.get("key"),
                        "content_length": entry.get("content_length"),
                    }
                )
                text_lines.append(summary)
            else:
                text_lines.append(
                    f"FAILED [{entry.get('index')}] {entry.get('s3_uri')}: {entry.get('error', 'unknown error')}"
                )

        yield self.create_json_message(json_payload)

        if ok_count == 0:
            yield self.create_text_message("All downloads failed:\n" + "\n\n".join(text_lines))
        else:
            yield self.create_text_message("\n\n".join(text_lines))

        # Emit successful blob payloads in input order. Failed entries simply
        # produce no blob (downstream nodes can correlate via the json results
        # list to see which indices succeeded).
        for file_bytes, blob_meta in blobs_to_yield:
            yield self.create_blob_message(file_bytes, meta=blob_meta)

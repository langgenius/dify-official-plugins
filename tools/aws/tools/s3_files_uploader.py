"""
Location: tools/s3_files_uploader.py
Purpose:  Batch-upload multiple files received from a prior Dify workflow node to a
          specified S3 bucket.

This tool is the array-input counterpart of ``s3_file_uploader``. It consumes a list
of binary assets (``input_files: array[file]``) from an upstream node and persists
each one to Amazon S3, optionally returning a presigned ``GET`` URL per object.

Per-file failures do NOT abort the batch: each file's outcome is captured in the
``results`` list with ``status = "ok" | "failed"`` (and an ``error`` string on
failure). The whole invocation only emits a top-level error message when **every**
file fails (so downstream nodes see a clear failure signal).
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
# Mirrors the helpers in the single-file s3_file_uploader so the two tools stay
# byte-for-byte consistent on credential resolution rules.
# ---------------------------------------------------------------------------


def _resolve_aws_credentials(
    tool: Any, tool_parameters: dict[str, Any]
) -> dict[str, Optional[str]]:
    """Merge provider-level credentials with per-invocation tool parameters."""
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
    """Safely coerce the ``presign_expiry`` parameter to int (matches single-file tool)."""
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _sanitize_prefix(prefix: Optional[str]) -> str:
    """Trim leading/trailing slashes from a prefix and tolerate empty input."""
    if not prefix:
        return ""
    return prefix.strip("/ ")


def _normalize_input_files(raw: Any) -> list[Any]:
    """Coerce the ``input_files`` parameter into a flat list.

    Dify passes ``array[file]`` parameters as a Python list, but be defensive in
    case a single file slips through (e.g. an upstream node that does not
    realize the parameter is an array). Treat ``None`` / empty as no input.
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        return [item for item in raw if item is not None]
    return [raw]


def _derive_object_key(input_file: Any, key_prefix: str) -> str:
    """Compute the final S3 object key for a single batch entry.

    The single-file ``s3_file_uploader`` accepts a user-supplied ``object_key``
    override, but for the batch tool a single override cannot apply to N files.
    Instead we always derive the base key from the file's own ``filename`` (or
    a UUID fallback) and optionally prepend ``key_prefix``.
    """
    requested_key = getattr(input_file, "filename", None)
    fallback_key = (
        getattr(input_file, "url", "").rstrip("/").split("/")[-1]
        if getattr(input_file, "url", None)
        else None
    )
    object_key = requested_key or fallback_key or f"dify-upload-{uuid.uuid4().hex}"
    object_key = object_key.lstrip("/")
    if key_prefix:
        object_key = f"{key_prefix}/{object_key}"
    return object_key


# ---------------------------------------------------------------------------
# Tool implementation
# ---------------------------------------------------------------------------


class S3FilesUploader(Tool):
    """Batch-upload Dify file variables to S3.

    The boto3 client is created once per ``_invoke`` call (not cached on
    ``self``) for the same per-tenant safety reason as ``s3_file_uploader``.
    Within a single invocation the client is reused across all batch entries,
    which is safe because all entries share the same credential bundle.
    """

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Read all input files, upload them, and emit aggregated results."""
        # Initialize the S3 client up front. A failure here aborts the whole
        # batch because no per-file work can succeed without a client.
        try:
            credentials = _resolve_aws_credentials(self, tool_parameters)
            client_kwargs = _build_boto3_client_kwargs(credentials)
            s3_client = boto3.client("s3", **client_kwargs)
        except Exception as exc:  # pragma: no cover - boto3 init errors
            yield self.create_text_message(f"Failed to initialize AWS client: {exc}")
            return

        input_files = _normalize_input_files(tool_parameters.get("input_files"))
        if not input_files:
            yield self.create_text_message(
                "input_files parameter is required and must not be empty"
            )
            return

        bucket_name = tool_parameters.get("bucket_name")
        if not bucket_name:
            yield self.create_text_message("bucket_name parameter is required")
            return

        key_prefix = _sanitize_prefix(tool_parameters.get("key_prefix"))
        generate_presign = bool(tool_parameters.get("generate_presign_url"))
        expiry_seconds = _parse_presign_expiry(tool_parameters.get("presign_expiry"))

        # Track keys we've already used so a duplicate filename in the same
        # batch (e.g. two `image.png` from different upstream branches) does
        # not silently overwrite. We append `-{n}` to disambiguate.
        used_keys: set[str] = set()
        results: list[dict[str, Any]] = []

        for index, input_file in enumerate(input_files):
            entry: dict[str, Any] = {
                "index": index,
                "bucket_name": bucket_name,
            }

            # Read bytes
            try:
                file_bytes: bytes = input_file.blob  # type: ignore[attr-defined]
            except Exception as exc:
                entry["status"] = "failed"
                entry["error"] = f"Failed to read input file at index {index}: {exc}"
                results.append(entry)
                continue

            base_key = _derive_object_key(input_file, key_prefix)
            object_key = base_key
            dedup_counter = 1
            while object_key in used_keys:
                # Insert the disambiguator before the final extension when one
                # is present; otherwise append.
                if "." in base_key.rsplit("/", 1)[-1]:
                    head, _, tail = base_key.rpartition(".")
                    object_key = f"{head}-{dedup_counter}.{tail}"
                else:
                    object_key = f"{base_key}-{dedup_counter}"
                dedup_counter += 1
            used_keys.add(object_key)
            entry["object_key"] = object_key
            entry["s3_uri"] = f"s3://{bucket_name}/{object_key}"

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
                entry["status"] = "failed"
                entry["error"] = f"Failed to upload to S3: {error_message}"
                results.append(entry)
                continue
            except Exception as exc:
                entry["status"] = "failed"
                entry["error"] = f"Failed to upload to S3: {exc}"
                results.append(entry)
                continue

            entry["status"] = "ok"

            if generate_presign:
                try:
                    presigned_url = s3_client.generate_presigned_url(
                        "get_object",
                        Params={"Bucket": bucket_name, "Key": object_key},
                        ExpiresIn=expiry_seconds,
                    )
                    entry["presigned_url"] = presigned_url
                    entry["presign_expiry"] = expiry_seconds
                except Exception as exc:
                    # generate_presigned_url is a client-side operation that
                    # can raise ClientError, ParamValidationError, other
                    # BotoCoreError subclasses, or unrelated runtime errors.
                    # The upload itself already succeeded, so we surface the
                    # presign failure as a per-entry warning (`presign_error`)
                    # rather than failing the whole batch.
                    if isinstance(exc, ClientError):
                        error_message = exc.response.get("Error", {}).get("Message", str(exc))
                    else:
                        error_message = str(exc)
                    entry["presign_error"] = error_message

            results.append(entry)

        ok_count = sum(1 for r in results if r.get("status") == "ok")
        failed_count = len(results) - ok_count

        json_payload = {
            "count": len(results),
            "ok": ok_count,
            "failed": failed_count,
            "results": results,
        }

        # Build a per-line text summary: presigned URL preferred when available,
        # otherwise s3_uri, otherwise an error marker.
        text_lines: list[str] = []
        for entry in results:
            if entry.get("status") == "ok":
                text_lines.append(entry.get("presigned_url") or entry.get("s3_uri", ""))
            else:
                text_lines.append(
                    f"FAILED [{entry.get('index')}]: {entry.get('error', 'unknown error')}"
                )

        yield self.create_json_message(json_payload)

        if ok_count == 0:
            yield self.create_text_message("All uploads failed:\n" + "\n".join(text_lines))
        else:
            yield self.create_text_message("\n".join(text_lines))

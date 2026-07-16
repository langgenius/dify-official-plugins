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
import requests
from botocore.exceptions import ClientError

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

try:  # pragma: no cover - import shape varies across SDK versions
    from dify_plugin.file.file import File as _DifyFile
except Exception:  # pragma: no cover - older SDK or refactor
    _DifyFile = None  # type: ignore[assignment]

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


# ---------------------------------------------------------------------------
# Server-side encryption helpers
# ---------------------------------------------------------------------------

_VALID_SSE_TYPES: tuple[str, ...] = ("AES256", "aws:kms", "aws:kms:dsse")


def _build_sse_put_object_kwargs(tool_parameters: dict[str, Any]) -> dict[str, Any]:
    """Return the optional ``put_object`` kwargs that toggle server-side encryption.

    Returns an empty dict when no SSE was requested. Raises ``ValueError`` for
    invalid combinations so the batch invocation can fail loudly *before* it
    starts uploading half the batch with the wrong header.

    Recognised parameters:

    * ``sse_type``: "" / "AES256" / "aws:kms" / "aws:kms:dsse".
      Empty string (or missing) means "do not send any SSE header" so existing
      buckets that do not require encryption keep their old behavior.
    * ``kms_key_id``: optional KMS identifier (key id, full ARN, or ``alias/...``).
      Only honored when ``sse_type`` starts with ``aws:kms``. Empty string =
      use the bucket's default KMS key.
    * ``bucket_key_enabled``: optional boolean to turn on S3 Bucket Keys for
      KMS. Reduces ``kms:GenerateDataKey`` calls ~99% by reusing a bucket-scoped
      data key. Only honored when ``sse_type`` starts with ``aws:kms``.

    Background: customer bucket policies frequently include a Deny clause like
    ``Effect: Deny`` + ``Condition: { StringNotEquals: { s3:x-amz-server-side-encryption: aws:kms } }``
    which rejects PutObject without an explicit ``aws:kms`` SSE header. The old
    uploader always sent the header unset, which produced the
    ``not authorized to perform: s3:PutObject ... explicit deny in a resource-based policy``
    error customers reported. Setting ``sse_type='aws:kms'`` lets boto3 attach
    ``x-amz-server-side-encryption: aws:kms`` so the bucket policy condition is
    satisfied.
    """
    raw_sse = tool_parameters.get("sse_type")
    sse = (raw_sse or "").strip()
    if not sse:
        return {}
    if sse not in _VALID_SSE_TYPES:
        raise ValueError(
            f"Invalid sse_type '{sse}'. Allowed values: '' (none), 'AES256', "
            f"'aws:kms', 'aws:kms:dsse'."
        )

    sse_kwargs: dict[str, Any] = {"ServerSideEncryption": sse}

    if sse.startswith("aws:kms"):
        kms_key_id = (tool_parameters.get("kms_key_id") or "").strip()
        if kms_key_id:
            sse_kwargs["SSEKMSKeyId"] = kms_key_id
        if bool(tool_parameters.get("bucket_key_enabled")):
            sse_kwargs["BucketKeyEnabled"] = True
    else:
        # Surface a config mistake early: kms_key_id makes no sense for AES256.
        if (tool_parameters.get("kms_key_id") or "").strip():
            raise ValueError(
                "kms_key_id is only meaningful when sse_type='aws:kms' or "
                "'aws:kms:dsse'. Clear kms_key_id or switch sse_type."
            )
        if bool(tool_parameters.get("bucket_key_enabled")):
            raise ValueError(
                "bucket_key_enabled is only meaningful when sse_type='aws:kms' "
                "or 'aws:kms:dsse'. Clear bucket_key_enabled or switch sse_type."
            )

    return sse_kwargs


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


def _attr(input_file: Any, key: str, default: Any = None) -> Any:
    """Read ``key`` from either an SDK ``File`` object or a raw dict payload.

    The Dify plugin SDK's ``_convert_parameters`` only auto-promotes list items
    to ``File`` when **every** item carries ``dify_model_identity ==
    '__dify__file__'``. Some Dify backends ship file-list entries without that
    tag (especially when the upstream node is a START with ``file-list`` typed
    variable), so the batch tool can receive a list of *dicts* instead of
    ``File`` objects. Those dicts typically carry keys like ``filename``,
    ``mime_type``, ``url``, ``transfer_method``, etc. — but not as attributes,
    so plain ``getattr`` would always return ``default``.
    """
    if isinstance(input_file, dict):
        return input_file.get(key, default)
    return getattr(input_file, key, default)


def _read_input_file_bytes(input_file: Any) -> bytes:
    """Return raw bytes for a single batch entry.

    Tries every shape the SDK / Dify backend might hand us:

    * ``File`` SDK object → ``.blob`` (downloads via the SDK's httpx call)
    * ``dict`` with inline ``blob`` (already-bytes upload)
    * ``dict`` with ``url`` / ``remote_url`` → fetched via ``requests.get``
    """
    # Path A: SDK File-like object
    blob = getattr(input_file, "blob", None)
    if isinstance(blob, (bytes, bytearray)):
        return bytes(blob)

    # Path B: dict payload (the case that crashes 0.0.28 with
    # ``'dict' object has no attribute 'blob'``)
    if isinstance(input_file, dict):
        # B1: when the SDK class exists, try wrapping the dict so we benefit
        #     from File.blob's caching/httpx logic.
        url = input_file.get("url") or input_file.get("remote_url")
        if _DifyFile is not None and isinstance(url, str) and url:
            try:
                return _DifyFile(url=url).blob  # type: ignore[no-any-return]
            except Exception:  # noqa: BLE001 - fall through to manual fetch
                pass

        # B2: plain HTTP fetch fallback
        if isinstance(url, str) and url:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            return resp.content

    raise TypeError(
        f"Cannot read bytes from input file of type {type(input_file).__name__}; "
        f"keys={list(input_file.keys()) if isinstance(input_file, dict) else 'n/a'}"
    )


def _derive_object_key(input_file: Any, key_prefix: str) -> str:
    """Compute the final S3 object key for a single batch entry.

    The single-file ``s3_file_uploader`` accepts a user-supplied ``object_key``
    override, but for the batch tool a single override cannot apply to N files.
    Instead we always derive the base key from the file's own ``filename`` (or
    a UUID fallback) and optionally prepend ``key_prefix``.
    """
    requested_key = _attr(input_file, "filename")
    url_value = _attr(input_file, "url") or _attr(input_file, "remote_url")
    fallback_key = (
        url_value.rstrip("/").split("/")[-1] if isinstance(url_value, str) and url_value else None
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

        # Resolve SSE kwargs once per batch (all entries share the same
        # encryption settings). A misconfiguration here aborts the whole batch
        # because uploading even one object with the wrong header creates
        # diverging encryption state in the bucket.
        try:
            sse_put_kwargs = _build_sse_put_object_kwargs(tool_parameters)
        except ValueError as exc:
            yield self.create_text_message(f"Server-side encryption misconfigured: {exc}")
            return

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

            # Read bytes (handles File SDK objects and raw dict payloads)
            try:
                file_bytes: bytes = _read_input_file_bytes(input_file)
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

            content_type = _attr(input_file, "mime_type") or "application/octet-stream"
            try:
                s3_client.put_object(
                    Bucket=bucket_name,
                    Key=object_key,
                    Body=file_bytes,
                    ContentType=content_type,
                    **sse_put_kwargs,
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
            # Echo SSE settings into the per-file result for downstream nodes
            # / observability without re-parsing the put_object response.
            if sse_put_kwargs.get("ServerSideEncryption"):
                entry["server_side_encryption"] = sse_put_kwargs["ServerSideEncryption"]
                if sse_put_kwargs.get("SSEKMSKeyId"):
                    entry["kms_key_id"] = sse_put_kwargs["SSEKMSKeyId"]
                if sse_put_kwargs.get("BucketKeyEnabled"):
                    entry["bucket_key_enabled"] = True

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

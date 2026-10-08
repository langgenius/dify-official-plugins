"""Shared behaviour of the MinerU tools: options, polling and emitting results."""

import logging
import time
from collections.abc import Callable, Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.invocations.file import UploadFileResponse

from utils import results
from utils.client import (
    API_CLOUD_V4,
    API_LOCAL_V1,
    STATE_DONE,
    CloudV4Client,
    Credentials,
    JobStatus,
    LocalLegacyClient,
    LocalV1Client,
    MineruNetworkError,
    ParseOptions,
    make_client,
    parse_extra_formats,
)

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 540
MAX_POLL_INTERVAL_SECONDS = 10
MAX_CONSECUTIVE_POLL_ERRORS = 3


def _bool(value: Any, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


class MineruBaseTool(Tool):
    def _credentials(self) -> Credentials:
        return Credentials.from_mapping(self.runtime.credentials)

    @staticmethod
    def _timeout(tool_parameters: dict[str, Any]) -> float:
        try:
            timeout = float(tool_parameters.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS)
        except (TypeError, ValueError):
            timeout = DEFAULT_TIMEOUT_SECONDS
        return max(timeout, 10)

    @staticmethod
    def _wait(tool_parameters: dict[str, Any]) -> bool:
        return _bool(tool_parameters.get("wait_for_result"), True)

    @staticmethod
    def _options(tool_parameters: dict[str, Any]) -> ParseOptions:
        return ParseOptions(
            model_version=tool_parameters.get("model_version") or "pipeline",
            enable_ocr=_bool(tool_parameters.get("enable_ocr"), False),
            language=(tool_parameters.get("language") or "auto").strip(),
            extra_formats=parse_extra_formats(tool_parameters.get("extra_formats")),
            enable_formula=_bool(tool_parameters.get("enable_formula"), True),
            enable_table=_bool(tool_parameters.get("enable_table"), True),
            parse_method=tool_parameters.get("parse_method") or "auto",
            page_ranges=(tool_parameters.get("page_ranges") or "").strip(),
            backend=tool_parameters.get("backend") or "pipeline",
            server_url=(tool_parameters.get("server_url") or "").strip(),
            tier=(tool_parameters.get("tier") or "").strip(),
        )

    @staticmethod
    def _client(credentials: Credentials, timeout: float) -> CloudV4Client | LocalV1Client | LocalLegacyClient:
        return make_client(credentials, timeout=min(timeout, 120))

    @staticmethod
    def _poll(fetch: Callable[[], JobStatus], first: JobStatus, timeout: float) -> JobStatus:
        """Poll until the job is done or ``timeout`` seconds have passed; failures raise."""
        deadline = time.monotonic() + timeout
        status, interval, errors = first, 2.0, 0
        while status.state != STATE_DONE:
            if time.monotonic() + interval > deadline:
                return status
            time.sleep(interval)
            interval = min(interval * 1.5, MAX_POLL_INTERVAL_SECONDS)
            try:
                status = fetch()
                errors = 0
            except MineruNetworkError as e:
                # Job failures and auth errors are final; only network hiccups are retried.
                errors += 1
                if errors >= MAX_CONSECUTIVE_POLL_ERRORS:
                    raise
                logger.warning(f"Polling MinerU failed, retrying: {e}")
        return status

    def _emit_pending(self, status: JobStatus, server_type: str) -> Generator[ToolInvokeMessage, None, None]:
        job_ref = f"task_id={status.task_id}" if status.task_id else f"batch_id={status.batch_id}"
        progress = f" Progress: {status.progress}." if status.progress else ""
        yield self.create_text_message(
            f"MinerU is still parsing ({status.state}, {job_ref}).{progress} "
            f"Call get-parse-result with this {job_ref.split('=')[0]} to fetch the result later."
        )
        yield self.create_json_message(
            {"task_id": status.task_id, "batch_id": status.batch_id, "state": status.state, "progress": status.progress}
        )
        yield from self._emit_variables(status, server_type, images=[])

    def _emit_variables(
        self, status: JobStatus, server_type: str, images: list[UploadFileResponse]
    ) -> Generator[ToolInvokeMessage, None, None]:
        yield self.create_variable_message("images", images)
        yield self.create_variable_message("full_zip_url", status.full_zip_url)
        yield self.create_variable_message("task_id", status.task_id)
        yield self.create_variable_message("batch_id", status.batch_id)
        yield self.create_variable_message("state", status.state)
        yield self.create_variable_message("server_type", server_type)

    def _emit_document(
        self,
        client: CloudV4Client | LocalV1Client | LocalLegacyClient,
        status: JobStatus,
        server_type: str,
        source_name: str,
    ) -> Generator[ToolInvokeMessage, None, None]:
        if status.api == API_CLOUD_V4:
            document = results.from_cloud_zip(client.fetch_zip(status))
        elif status.api == API_LOCAL_V1:
            document = results.from_v1_zip(status.zip_bytes or b"", status.extra_files, source_name)
        else:
            document = results.from_legacy_response(status.legacy_response or {}, status.legacy_version)

        images: list[UploadFileResponse] = []
        for image in document.images:
            try:
                uploaded = self.session.file.upload(image.name, image.data, image.mime_type)
            except Exception as e:
                logger.error(f"Failed to upload image {image.name} to Dify: {e}")
                continue
            images.append(uploaded)
            if not uploaded.preview_url:
                yield self.create_blob_message(image.data, meta={"filename": image.name, "mime_type": image.mime_type})

        for extra in document.extra_files:
            yield self.create_blob_message(extra.data, meta={"filename": extra.name, "mime_type": extra.mime_type})

        for payload in document.json_messages:
            yield self.create_json_message(payload)
        yield self.create_text_message(self.replace_md_img_path(document.markdown, images))
        yield from self._emit_variables(status, server_type, images)

    @staticmethod
    def replace_md_img_path(markdown: str, images: list[UploadFileResponse]) -> str:
        """Point Markdown image links (images/xxx.jpg) at the files uploaded to Dify."""
        for image in images:
            if image.preview_url:
                markdown = markdown.replace(f"images/{image.name}", image.preview_url)
        return markdown

    def _finish(
        self,
        client: CloudV4Client | LocalV1Client | LocalLegacyClient,
        status: JobStatus,
        fetch: Callable[[], JobStatus],
        tool_parameters: dict[str, Any],
        server_type: str,
        source_name: str,
    ) -> Generator[ToolInvokeMessage, None, None]:
        if status.state != STATE_DONE and self._wait(tool_parameters):
            status = self._poll(fetch, status, self._timeout(tool_parameters))
        if status.state != STATE_DONE:
            yield from self._emit_pending(status, server_type)
            return
        yield from self._emit_document(client, status, server_type, source_name)

import base64
import logging
import time
from pathlib import Path
from tempfile import SpooledTemporaryFile

from dify_plugin.entities.model.message import DocumentPromptMessageContent
from dify_plugin.errors.model import (
    InvokeBadRequestError,
    InvokeServerUnavailableError,
)
from openai import OpenAI

FILE_PROCESSING_POLL_INTERVAL_SECONDS = 5
FILE_PROCESSING_TIMEOUT_SECONDS = 240
# ponytail: pace each invocation only; add a shared limiter if this becomes high traffic.
FILE_UPLOAD_INTERVAL_SECONDS = 0.35
FILE_REQUEST_INTERVAL_SECONDS = 0.1
FILE_CLEANUP_TIMEOUT_SECONDS = 10
FILE_READ_CHUNK_BYTES = 1024 * 1024
IMAGE_MAX_BYTES = 20 * 1024 * 1024
DOCUMENT_MAX_BYTES = 150 * 1024 * 1024
MAX_DOCUMENT_INPUT_BASE64_BYTES = 4 * ((DOCUMENT_MAX_BYTES + 2) // 3)
IMAGE_FORMATS = {"bmp", "gif", "jpeg", "jpg", "png"}

logger = logging.getLogger(__name__)


class QwenLongFiles:
    def __init__(self, client: OpenAI) -> None:
        self.client = client
        self.uploaded_ids: list[str] = []

    def upload(self, content: DocumentPromptMessageContent) -> str:
        if self.uploaded_ids:
            time.sleep(FILE_UPLOAD_INTERVAL_SECONDS)

        filename = Path(content.filename).name or (
            f"document.{content.format.lstrip('.')}"
        )
        max_bytes = (
            IMAGE_MAX_BYTES
            if content.mime_type.lower().startswith("image/")
            or content.format.lower().lstrip(".") in IMAGE_FORMATS
            else DOCUMENT_MAX_BYTES
        )

        with SpooledTemporaryFile(max_size=FILE_READ_CHUNK_BYTES) as file:
            self._write_content(file, content, max_bytes)
            file.seek(0)
            uploaded = self.client.files.create(
                file=(filename, file, content.mime_type or None),
                purpose="file-extract",
            )
            self.uploaded_ids.append(uploaded.id)

        return uploaded.id

    def wait_until_processed(self) -> None:
        deadline = time.monotonic() + FILE_PROCESSING_TIMEOUT_SECONDS
        for index, file_id in enumerate(self.uploaded_ids):
            if index:
                time.sleep(FILE_REQUEST_INTERVAL_SECONDS)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise InvokeServerUnavailableError(
                    "Timed out waiting for Qwen-Long documents to be processed."
                )
            try:
                processed = self.client.files.wait_for_processing(
                    file_id,
                    poll_interval=FILE_PROCESSING_POLL_INTERVAL_SECONDS,
                    max_wait_seconds=remaining,
                )
            except RuntimeError as exc:
                raise InvokeServerUnavailableError(
                    "Timed out waiting for Qwen-Long documents to be processed."
                ) from exc

            status = getattr(processed.status, "value", processed.status)
            if status != "processed":
                details = getattr(processed, "status_details", None) or getattr(
                    processed, "error", None
                )
                message = f"Qwen-Long document processing ended with status {status}."
                if details:
                    message = f"{message} {details}"
                raise InvokeBadRequestError(message)

    def cleanup(self) -> None:
        remaining = list(self.uploaded_ids)
        for attempt in range(2):
            failed = []
            for index, file_id in enumerate(remaining):
                if index or attempt:
                    time.sleep(FILE_REQUEST_INTERVAL_SECONDS)
                try:
                    deleted = self.client.files.delete(
                        file_id,
                        timeout=FILE_CLEANUP_TIMEOUT_SECONDS,
                    )
                    if deleted.deleted is not True:
                        failed.append(file_id)
                except Exception:  # noqa: BLE001 - cleanup must remain best effort
                    failed.append(file_id)
            remaining = failed
            if not remaining:
                break
        for file_id in remaining:
            logger.warning("Failed to delete temporary Qwen-Long file %s.", file_id)
        self.uploaded_ids.clear()
        try:
            self.client.close()
        except Exception:
            logger.warning("Failed to close Qwen-Long file client.", exc_info=True)

    @staticmethod
    def _write_content(
        file,
        content: DocumentPromptMessageContent,
        max_bytes: int,
    ) -> None:
        if not content.base64_data:
            raise InvokeBadRequestError(
                "Qwen-Long document content requires base64 data; set "
                "MULTIMODAL_SEND_FORMAT=base64."
            )

        max_encoded_bytes = 4 * ((max_bytes + 2) // 3)
        if len(content.base64_data) > max_encoded_bytes:
            raise InvokeBadRequestError(
                "Qwen-Long document exceeds the supported file size."
            )

        size = 0
        try:
            for offset in range(0, len(content.base64_data), FILE_READ_CHUNK_BYTES):
                encoded_chunk = content.base64_data[
                    offset : offset + FILE_READ_CHUNK_BYTES
                ]
                if (
                    offset + FILE_READ_CHUNK_BYTES < len(content.base64_data)
                    and "=" in encoded_chunk
                ):
                    raise InvokeBadRequestError(
                        "Qwen-Long document contains invalid base64 data."
                    )
                chunk = base64.b64decode(
                    encoded_chunk,
                    validate=True,
                )
                size += len(chunk)
                if size > max_bytes:
                    raise InvokeBadRequestError(
                        "Qwen-Long document exceeds the supported file size."
                    )
                file.write(chunk)
        except ValueError as exc:
            raise InvokeBadRequestError(
                "Qwen-Long document contains invalid base64 data."
            ) from exc

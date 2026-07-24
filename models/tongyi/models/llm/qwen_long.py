import base64
import os
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

import requests
from dify_plugin.entities.model.message import DocumentPromptMessageContent
from openai import OpenAI

FILE_DOWNLOAD_TIMEOUT_SECONDS = 60
FILE_PROCESSING_POLL_INTERVAL_SECONDS = 5
FILE_PROCESSING_TIMEOUT_SECONDS = 300
PENDING_FILE_STATUSES = {"processing", "uploaded"}


class QwenLongFileUploader:
    def __init__(self, client: OpenAI) -> None:
        self.client = client

    def upload(self, content: DocumentPromptMessageContent) -> str:
        payload = self._read_payload(content)
        filename = self._filename(content)
        suffix = Path(filename).suffix
        temp_file_path = None

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_file.write(payload)
                temp_file.flush()
                temp_file_path = temp_file.name

            with open(temp_file_path, "rb") as file:
                uploaded_file = self.client.files.create(
                    file=(filename, file, content.mime_type or None),
                    purpose="file-extract",
                )

            processed_file = self._wait_until_processed(uploaded_file)
            return processed_file.id
        finally:
            if temp_file_path:
                with suppress(FileNotFoundError, PermissionError):
                    os.unlink(temp_file_path)

    @staticmethod
    def _read_payload(content: DocumentPromptMessageContent) -> bytes:
        if content.base64_data:
            return base64.b64decode(content.base64_data)

        if not content.url:
            raise ValueError(
                "Qwen-Long document content requires base64 data or a URL."
            )

        try:
            response = requests.get(
                content.url,
                timeout=FILE_DOWNLOAD_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise ValueError(
                f"Failed to fetch Qwen-Long document from {content.url}"
            ) from exc
        return response.content

    @staticmethod
    def _filename(content: DocumentPromptMessageContent) -> str:
        if content.filename:
            return Path(content.filename).name
        if content.format:
            return f"document.{content.format.lstrip('.')}"
        return "document"

    def _wait_until_processed(self, uploaded_file: Any) -> Any:
        deadline = time.monotonic() + FILE_PROCESSING_TIMEOUT_SECONDS
        current_file = uploaded_file

        while self._status(current_file) in PENDING_FILE_STATUSES:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Timed out waiting for Qwen-Long file {current_file.id} to be processed."
                )
            time.sleep(FILE_PROCESSING_POLL_INTERVAL_SECONDS)
            current_file = self.client.files.retrieve(current_file.id)

        if self._status(current_file) == "error":
            details = getattr(current_file, "status_details", None) or getattr(
                current_file, "error", None
            )
            message = f"Failed to process Qwen-Long file {current_file.id}."
            if details:
                message = f"{message} {details}"
            raise ValueError(message)

        return current_file

    @staticmethod
    def _status(file: Any) -> str:
        status = getattr(file, "status", "")
        if hasattr(status, "value"):
            status = status.value
        return str(status or "").lower()

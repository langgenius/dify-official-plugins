import base64
import hashlib
import logging
import os
import tempfile
import time
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from enum import Enum
from typing import Any

import requests
from dify_plugin.entities.model.message import (
    MultiModalPromptMessageContent,
    PromptMessageContentType,
)
from google import genai
from google.genai import types

from .model_schema import INLINE_FILE_PARAMETER_NAME
from .utils import UNSUPPORTED_DOCUMENT_TYPES, UNSUPPORTED_EXTENSIONS, FileCache

FILE_DOWNLOAD_TIMEOUT_SECONDS = 60
GOOGLE_FILE_CACHE_TTL_SECONDS = 47 * 60 * 60


class GeminiFileMode(Enum):
    FILES_API = "files_api"
    INLINE = "inline"

    @classmethod
    def from_parameters(
        cls, model_parameters: Mapping[str, Any] | None
    ) -> "GeminiFileMode":
        if model_parameters and model_parameters.get(INLINE_FILE_PARAMETER_NAME, False):
            return cls.INLINE
        return cls.FILES_API


@dataclass(frozen=True)
class GeminiFilePayload:
    data: bytes
    mime_type: str


@dataclass(frozen=True)
class UploadedGeminiFile:
    uri: str
    mime_type: str


class GeminiFilePartFactory:
    def __init__(
        self,
        *,
        genai_client: genai.Client | None,
        file_server_url_prefix: str | None,
        cache: FileCache,
        mode: GeminiFileMode,
    ) -> None:
        self.genai_client = genai_client
        self.file_server_url_prefix = file_server_url_prefix
        self.cache = cache
        self.mode = mode

    def build_part(
        self, message_content: MultiModalPromptMessageContent
    ) -> types.Part | None:
        if not self.is_supported(message_content):
            logging.debug(
                "Skipping unsupported file for Gemini: type=%s, mime_type=%s, format=%s",
                message_content.type,
                message_content.mime_type,
                message_content.format,
            )
            return None

        payload = self.read_payload(message_content)
        if self.mode is GeminiFileMode.INLINE:
            return types.Part.from_bytes(data=payload.data, mime_type=payload.mime_type)

        uploaded_file = self.upload_payload(payload)
        return types.Part.from_uri(
            file_uri=uploaded_file.uri,
            mime_type=uploaded_file.mime_type,
        )

    @staticmethod
    def is_supported(message_content: MultiModalPromptMessageContent) -> bool:
        if message_content.type != PromptMessageContentType.DOCUMENT:
            return True

        if message_content.mime_type in UNSUPPORTED_DOCUMENT_TYPES:
            return False

        if (
            message_content.format
            and message_content.format.lower() in UNSUPPORTED_EXTENSIONS
        ):
            return False

        return True

    def read_payload(
        self, message_content: MultiModalPromptMessageContent
    ) -> GeminiFilePayload:
        if message_content.base64_data:
            data = base64.b64decode(message_content.base64_data)
        else:
            file_url = self._resolve_file_url(message_content)
            try:
                response = requests.get(file_url, timeout=FILE_DOWNLOAD_TIMEOUT_SECONDS)
                response.raise_for_status()
            except requests.exceptions.RequestException as exc:
                raise ValueError(f"Failed to fetch data from url {file_url}") from exc
            data = response.content

        return GeminiFilePayload(
            data=data,
            mime_type=self._normalized_mime_type(message_content),
        )

    def upload_payload(self, payload: GeminiFilePayload) -> UploadedGeminiFile:
        if self.genai_client is None:
            raise ValueError("Gemini client is required to upload files.")

        cache_key = self._cache_key(payload)
        if self.cache.exists(cache_key):
            cached_uri, cached_mime_type = self.cache.get(cache_key).split(
                ";", maxsplit=1
            )
            return UploadedGeminiFile(uri=cached_uri, mime_type=cached_mime_type)

        temp_file_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file.write(payload.data)
                temp_file.flush()
                temp_file_path = temp_file.name

            file = self.genai_client.files.upload(
                file=temp_file_path,
                config=types.UploadFileConfig(mime_type=payload.mime_type),
            )

            while file.state.name == "PROCESSING":
                time.sleep(5)
                file = self.genai_client.files.get(name=file.name)

            uploaded_file = UploadedGeminiFile(uri=file.uri, mime_type=file.mime_type)
            self.cache.setex(
                cache_key,
                GOOGLE_FILE_CACHE_TTL_SECONDS,
                f"{uploaded_file.uri};{uploaded_file.mime_type}",
            )
            return uploaded_file
        finally:
            if temp_file_path:
                with suppress(FileNotFoundError, PermissionError):
                    os.unlink(temp_file_path)

    def _resolve_file_url(self, message_content: MultiModalPromptMessageContent) -> str:
        file_url = message_content.url
        if not file_url:
            raise ValueError("File URL is missing in message content.")

        if file_url.startswith(("https://", "http://")):
            return file_url

        if self.file_server_url_prefix:
            prefix = self.file_server_url_prefix.rstrip("/")
            if "/files" in file_url:
                file_url = f"{prefix}/files{file_url.split('/files', maxsplit=1)[-1]}"
            else:
                file_url = f"{prefix}/{file_url.lstrip('/')}"

        if not file_url.startswith(("https://", "http://")):
            raise ValueError("Set FILES_URL env first! Or provide an absolute URL.")

        return file_url

    @staticmethod
    def _normalized_mime_type(message_content: MultiModalPromptMessageContent) -> str:
        if (
            message_content.type == PromptMessageContentType.DOCUMENT
            and message_content.format == "md"
        ):
            return "text/markdown"

        return message_content.mime_type or ""

    @staticmethod
    def _cache_key(payload: GeminiFilePayload) -> str:
        digest = hashlib.sha256()
        digest.update(payload.mime_type.encode("utf-8"))
        digest.update(b"\0")
        digest.update(payload.data)
        return f"gemini-file:{digest.hexdigest()}"

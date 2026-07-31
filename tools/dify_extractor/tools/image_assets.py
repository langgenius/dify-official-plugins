"""Bounded, best-effort image download and upload support."""

from __future__ import annotations

import logging
import mimetypes
import uuid
from dataclasses import dataclass
from urllib.parse import urlparse

import requests
from dify_plugin import Tool
from dify_plugin.invocations.file import UploadFileResponse

MAX_IMAGES = 20
MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_TOTAL_IMAGE_BYTES = 100 * 1024 * 1024
IMAGE_DOWNLOAD_TIMEOUT = 30
IMAGE_DOWNLOAD_CHUNK_SIZE = 64 * 1024


@dataclass(frozen=True, slots=True)
class ImageAsset:
    file: UploadFileResponse
    markdown: str


def is_http_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme.casefold() in {"http", "https"} and bool(parsed.netloc)


class ImageAssetService:
    """Uploads images without allowing image failures to abort extraction."""

    def __init__(self, tool: Tool, logger: logging.Logger | None = None) -> None:
        self._tool = tool
        self._logger = logger or logging.getLogger(__name__)
        self._attempted = 0
        self._consumed_bytes = 0

    def upload_embedded(
        self,
        content: bytes,
        *,
        extension: str | None = None,
        mime_type: str | None = None,
        source: str = "embedded image",
    ) -> ImageAsset | None:
        if not self._reserve_attempt(source):
            return None
        resolved_mime = self._resolve_mime_type(mime_type, extension)
        if not resolved_mime:
            self._logger.warning("Skipping %s with an unknown image type", source)
            return None
        return self._upload_bytes(content, resolved_mime, extension, source)

    def download_and_upload(self, url: str) -> ImageAsset | None:
        if not is_http_url(url):
            self._logger.warning("Skipping image with unsupported URL scheme: %s", url)
            return None
        if not self._reserve_attempt(url):
            return None

        remaining = MAX_TOTAL_IMAGE_BYTES - self._consumed_bytes
        max_download = min(MAX_IMAGE_BYTES, remaining)
        if max_download <= 0:
            self._logger.warning("Skipping image because the cumulative image budget is exhausted")
            return None

        try:
            with requests.get(
                url,
                stream=True,
                timeout=IMAGE_DOWNLOAD_TIMEOUT,
            ) as response:
                response.raise_for_status()
                final_url = getattr(response, "url", url)
                if not is_http_url(final_url):
                    raise ValueError("redirected to an unsupported URL scheme")

                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) > max_download:
                    raise ValueError("image exceeds the download limit")

                content = bytearray()
                for chunk in response.iter_content(chunk_size=IMAGE_DOWNLOAD_CHUNK_SIZE):
                    if not chunk:
                        continue
                    content.extend(chunk)
                    if len(content) > max_download:
                        raise ValueError("image exceeds the download limit")

                mime_type = self._remote_mime_type(response, final_url)
                if not mime_type:
                    raise ValueError("response is not a supported image")
                extension = mimetypes.guess_extension(mime_type)
                return self._upload_bytes(bytes(content), mime_type, extension, url)
        except (OSError, ValueError, requests.RequestException) as exc:
            self._logger.warning("Failed to import remote image %s: %s", url, exc)
            return None

    def _reserve_attempt(self, source: str) -> bool:
        if self._attempted >= MAX_IMAGES:
            self._logger.warning(
                "Skipping %s because the %d-image limit was reached", source, MAX_IMAGES
            )
            return False
        self._attempted += 1
        return True

    def _upload_bytes(
        self,
        content: bytes,
        mime_type: str,
        extension: str | None,
        source: str,
    ) -> ImageAsset | None:
        if not content:
            self._logger.warning("Skipping empty image from %s", source)
            return None
        if len(content) > MAX_IMAGE_BYTES:
            self._logger.warning("Skipping oversized image from %s", source)
            return None
        if self._consumed_bytes + len(content) > MAX_TOTAL_IMAGE_BYTES:
            self._logger.warning(
                "Skipping image from %s because the cumulative budget was reached", source
            )
            return None

        self._consumed_bytes += len(content)

        suffix = (
            self._normalize_extension(extension) or mimetypes.guess_extension(mime_type) or ".img"
        )
        file_name = f"{uuid.uuid4()}{suffix}"
        try:
            file_response = self._tool.session.file.upload(file_name, content, mime_type)
        except Exception as exc:
            self._logger.warning("Failed to upload image from %s: %s", source, exc)
            return None
        if not file_response.preview_url:
            self._logger.warning("Uploaded image from %s has no preview URL", source)
            return None

        return ImageAsset(
            file=file_response,
            markdown=f"![image]({file_response.preview_url})",
        )

    @staticmethod
    def _normalize_extension(extension: str | None) -> str | None:
        if not extension:
            return None
        normalized = extension.casefold().strip()
        return normalized if normalized.startswith(".") else f".{normalized}"

    @staticmethod
    def _resolve_mime_type(mime_type: str | None, extension: str | None) -> str | None:
        normalized = (mime_type or "").split(";", 1)[0].strip().casefold()
        if normalized.startswith("image/"):
            return normalized
        guessed, _ = mimetypes.guess_type(
            f"image{ImageAssetService._normalize_extension(extension) or ''}"
        )
        return guessed if guessed and guessed.startswith("image/") else None

    @staticmethod
    def _remote_mime_type(response: requests.Response, url: str) -> str | None:
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().casefold()
        if content_type.startswith("image/"):
            return content_type
        guessed, _ = mimetypes.guess_type(urlparse(url).path)
        return guessed if guessed and guessed.startswith("image/") else None

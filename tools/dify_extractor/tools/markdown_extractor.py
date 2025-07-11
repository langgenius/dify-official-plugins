"""Abstract interface for document loader implementations."""

import mimetypes
import re
import uuid
from pathlib import Path
from typing import Optional, cast
from urllib.parse import urlparse

import requests
from dify_plugin import Tool
from dify_plugin.invocations.file import UploadFileResponse

from tools.extractor_base import BaseExtractor
from tools.helpers import detect_file_encodings
from tools.document import Document, ExtractorResult


class MarkdownExtractor(BaseExtractor):
    """Load Markdown files.

    Args:
        file_bytes: Markdown content in bytes format.
        file_name: file name.
        tool: tool.
        remove_hyperlinks: remove hyperlinks.
        remove_images: remove images.
        encoding: encoding.
        autodetect_encoding: autodetect encoding.
    """

    def __init__(
        self,
        file_bytes: bytes,
        file_name: str,
        tool: Tool,
        remove_hyperlinks: bool = False,
        remove_images: bool = False,
        encoding: Optional[str] = None,
        autodetect_encoding: bool = True,
    ):
        """Initialize with file bytes."""
        self._file_bytes = file_bytes
        self._file_name = file_name
        self._tool = tool
        self._remove_hyperlinks = remove_hyperlinks
        self._remove_images = remove_images
        self._encoding = encoding
        self._autodetect_encoding = autodetect_encoding

    def extract(self) -> ExtractorResult:
        """Load from bytes."""
        md_content, tups, img_list = self.parse_tups()
        documents = []
        for header, value in tups:
            value = value.strip()
            if header is None:
                documents.append(Document(page_content=value))
            else:
                documents.append(Document(page_content=f"\n\n{header}\n{value}"))

        return ExtractorResult(
            md_content=md_content, documents=documents, img_list=img_list, origin_result=None
        )

    @staticmethod
    def _is_valid_url(url: str) -> bool:
        """Check if the url is valid."""
        parsed = urlparse(url)
        return bool(parsed.netloc) and bool(parsed.scheme)

    def markdown_to_tups(self, markdown_text: str) -> list[tuple[Optional[str], str]]:
        """Convert a markdown file to a dictionary.

        The keys are the headers and the values are the text under each header.

        """
        markdown_tups: list[tuple[Optional[str], str]] = []
        lines = markdown_text.split("\n")

        current_header = None
        current_text = ""
        code_block_flag = False

        for line in lines:
            if line.startswith("```"):
                code_block_flag = not code_block_flag
                current_text += line + "\n"
                continue
            if code_block_flag:
                current_text += line + "\n"
                continue
            header_match = re.match(r"^#+\s", line)
            if header_match:
                if current_header is not None:
                    markdown_tups.append((current_header, current_text))

                current_header = line
                current_text = ""
            else:
                current_text += line + "\n"
        markdown_tups.append((current_header, current_text))

        if current_header is not None:
            # pass linting, assert keys are defined
            markdown_tups = [
                (re.sub(r"#", "", cast(str, key)).strip(), re.sub(r"<.*?>", "", value))
                for key, value in markdown_tups
            ]
        else:
            markdown_tups = [
                (key, re.sub("\n", "", value)) for key, value in markdown_tups
            ]

        return markdown_tups

    def remove_images(self, content: str) -> str:
        """Get a dictionary of a markdown file from its path."""
        pattern = r"!{1}\[\[(.*)\]\]"
        content = re.sub(pattern, "", content)
        return content

    def remove_hyperlinks(self, content: str) -> str:
        """Get a dictionary of a markdown file from its path."""
        pattern = r"\[(.*?)\]\((.*?)\)"
        content = re.sub(pattern, r"\1", content)
        return content

    def parse_tups(self) -> tuple[str, list[tuple[Optional[str], str]], list[UploadFileResponse]]:
        """Parse bytes into tuples."""
        content = ""
        try:
            content = self._file_bytes.decode(
                self._encoding if self._encoding else "utf-8"
            )
        except UnicodeDecodeError as e:
            if self._autodetect_encoding:
                detected_encodings = detect_file_encodings(self._file_bytes)
                for encoding in detected_encodings:
                    try:
                        content = self._file_bytes.decode(encoding.encoding if encoding.encoding else "utf-8")
                        break
                    except UnicodeDecodeError:
                        continue
            else:
                raise RuntimeError("Error decoding markdown content") from e

        image_link_pattern = r"!\[.*?\]\((.*?)\)"
        img_url_list = re.findall(image_link_pattern, content)
        img_map = {}
        img_list = []
        for img_url in img_url_list:
            if not self._is_valid_url(img_url):
                continue
            response = requests.get(img_url)
            if response.status_code == 200:
                image_ext = mimetypes.guess_extension(response.headers["Content-Type"])
                if image_ext is None:
                    continue
                file_uuid = str(uuid.uuid4())
                file_name = file_uuid + "." + image_ext
                mime_type, _ = mimetypes.guess_type(file_name)

                file_res = self._tool.session.file.upload(
                    file_name, response.content, mime_type if mime_type else "image/png"
                )
                img_map[img_url] = file_res.preview_url
                img_list.append(file_res)
            else:
                continue

        for img_url, preview_url in img_map.items():
            content = content.replace(img_url, preview_url)
        if self._remove_hyperlinks:
            content = self.remove_hyperlinks(content)

        if self._remove_images:
            content = self.remove_images(content)

        return content, self._markdown_to_tups(content), img_list


    def _markdown_to_tups(self, markdown_text: str) -> list[tuple[Optional[str], str]]:
        """Convert a markdown file to a dictionary.

        The keys are the headers and the values are the text under each header.

        """
        markdown_tups: list[tuple[Optional[str], str]] = []
        lines = markdown_text.split("\n")

        current_header = None
        current_text = ""
        code_block_flag = False

        for line in lines:
            if line.startswith("```"):
                code_block_flag = not code_block_flag
                current_text += line + "\n"
                continue
            if code_block_flag:
                current_text += line + "\n"
                continue
            header_match = re.match(r"^#+\s", line)
            if header_match:
                markdown_tups.append((current_header, current_text))
                current_header = line
                current_text = ""
            else:
                current_text += line + "\n"
        markdown_tups.append((current_header, current_text))

        markdown_tups = [
            (re.sub(r"#", "", cast(str, key)).strip() if key else None, re.sub(r"<.*?>", "", value))
            for key, value in markdown_tups
        ]

        return markdown_tups

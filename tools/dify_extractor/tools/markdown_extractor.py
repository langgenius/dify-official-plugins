"""Markdown document extractor."""

import re

from tools.document import Document, ExtractorResult
from tools.extractor_base import BaseExtractor
from tools.helpers import decode_text

_REMOTE_IMAGE_PATTERN = re.compile(
    r"!\[(?P<alt>[^\]]*)\]\((?P<url>https?://[^\s)]+)(?P<title>\s+(?:\"[^\"]*\"|'[^']*'))?\)",
    re.IGNORECASE,
)
_FENCE_PATTERN = re.compile(r"^\s*(`{3,}|~{3,})")
_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


class MarkdownExtractor(BaseExtractor):
    def extract(self) -> ExtractorResult:
        content = decode_text(self.context.file_bytes, self.context.file_name)
        image_files = []
        image_service = self.context.image_service

        if image_service:

            def replace_remote_image(match: re.Match[str]) -> str:
                asset = image_service.download_and_upload(match.group("url"))
                if asset is None:
                    return match.group(0)
                image_files.append(asset.file)
                title = match.group("title") or ""
                return f"![{match.group('alt')}]({asset.file.preview_url}{title})"

            content = _REMOTE_IMAGE_PATTERN.sub(replace_remote_image, content)

        documents = [
            Document(
                page_content=section,
                metadata={"source": self.context.file_name},
            )
            for section in self._split_sections(content)
            if section.strip()
        ]
        return ExtractorResult(
            md_content=content,
            documents=documents,
            img_list=image_files,
        )

    @staticmethod
    def _split_sections(markdown_text: str) -> list[str]:
        sections: list[str] = []
        current_header: str | None = None
        current_lines: list[str] = []
        active_fence: str | None = None

        def flush() -> None:
            body = "\n".join(current_lines).strip()
            if current_header is not None:
                sections.append(f"{current_header}\n{body}".rstrip())
            elif body:
                sections.append(body)

        for line in markdown_text.splitlines():
            fence = _FENCE_PATTERN.match(line)
            if fence:
                marker = fence.group(1)[0]
                if active_fence is None:
                    active_fence = marker
                elif active_fence == marker:
                    active_fence = None
                current_lines.append(line)
                continue

            heading = _HEADING_PATTERN.match(line) if active_fence is None else None
            if heading:
                flush()
                current_header = heading.group(2).strip()
                current_lines = []
            else:
                current_lines.append(line)
        flush()
        return sections

import os
from collections.abc import Generator
from typing import Any

from dify_plugin.entities.tool import ToolInvokeMessage

from utils.client import CloudV4Client, LocalLegacyClient
from utils import tool_base

# Union of what the official API and the self-hosted MinerU versions accept; the server
# reports anything it cannot handle for the configured version.
SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsx",
    ".png",
    ".jpg",
    ".jpeg",
    ".jp2",
    ".webp",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
    ".html",
    ".htm",
    ".mhtml",
    ".mht",
    ".epub",
    ".ofd",
    ".odt",
    ".ods",
    ".odp",
    ".rtf",
    ".csv",
    ".tsv",
}


class MineruTool(tool_base.MineruBaseTool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        file = tool_parameters.get("file")
        if not file:
            raise ValueError("File is required")
        filename = file.filename or "document.pdf"
        extension = os.path.splitext(filename)[1].lower()
        if extension not in SUPPORTED_EXTENSIONS:
            raise ValueError(
                f"File extension {extension or '(none)'} is not supported. "
                f"Supported extensions: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
            )

        credentials = self._credentials()
        timeout = self._timeout(tool_parameters)
        options = self._options(tool_parameters)
        client = self._client(credentials, timeout)

        if isinstance(client, LocalLegacyClient):
            # MinerU 1.x-3.x /file_parse is synchronous: no task id, nothing to poll.
            status = client.parse_file(filename, file.blob, options, timeout)
            yield from self._emit_document(client, status, credentials.server_type, filename)
            return

        status = client.submit_file(filename, file.blob, options)
        if isinstance(client, CloudV4Client):
            fetch = lambda: client.get_batch(status.batch_id)  # noqa: E731
        else:
            fetch = lambda: client.get_job(status.task_id)  # noqa: E731
        yield from self._finish(client, status, fetch, tool_parameters, credentials.server_type, filename)

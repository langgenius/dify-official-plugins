import os
from collections.abc import Generator
from typing import Any
from urllib.parse import urlsplit

from dify_plugin.entities.tool import ToolInvokeMessage

from utils.client import CloudV4Client, LocalLegacyClient, MineruError
from utils import tool_base


class MineruParseUrlTool(tool_base.MineruBaseTool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        url = (tool_parameters.get("url") or "").strip()
        if not url:
            raise ValueError("URL is required")
        if urlsplit(url).scheme not in ("http", "https"):
            raise ValueError(f"URL must start with http:// or https://, got: {url}")

        credentials = self._credentials()
        timeout = self._timeout(tool_parameters)
        options = self._options(tool_parameters)
        client = self._client(credentials, timeout)

        if isinstance(client, LocalLegacyClient):
            raise MineruError(
                "Parsing from a URL needs the MinerU official API or a self-hosted MinerU 4.x server. "
                "This server runs MinerU 3.x or older; use parse-file instead."
            )

        status = client.submit_url(url, options)
        if isinstance(client, CloudV4Client):
            fetch = lambda: client.get_task(status.task_id)  # noqa: E731
        else:
            fetch = lambda: client.get_job(status.task_id)  # noqa: E731
        source_name = os.path.basename(urlsplit(url).path) or "document"
        yield from self._finish(client, status, fetch, tool_parameters, credentials.server_type, source_name)

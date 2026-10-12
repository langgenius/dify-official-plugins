from collections.abc import Generator
from typing import Any

from dify_plugin.entities.tool import ToolInvokeMessage

from utils.client import CloudV4Client, LocalLegacyClient, MineruError
from utils import tool_base


class MineruGetParseResultTool(tool_base.MineruBaseTool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        task_id = (tool_parameters.get("task_id") or "").strip()
        batch_id = (tool_parameters.get("batch_id") or "").strip()
        if not task_id and not batch_id:
            raise ValueError("Either task_id or batch_id is required")

        credentials = self._credentials()
        timeout = self._timeout(tool_parameters)
        client = self._client(credentials, timeout)

        if isinstance(client, LocalLegacyClient):
            raise MineruError(
                "This MinerU server runs MinerU 3.x or older, which parses synchronously and has no task ids. "
                "parse-file already returns the full result."
            )
        if isinstance(client, CloudV4Client):
            if task_id:
                fetch = lambda: client.get_task(task_id)  # noqa: E731
            else:
                fetch = lambda: client.get_batch(batch_id)  # noqa: E731
        else:
            if not task_id:
                raise ValueError("A self-hosted MinerU 4.x server identifies jobs by task_id; batch_id is not used.")
            fetch = lambda: client.get_job(task_id)  # noqa: E731

        status = fetch()
        yield from self._finish(
            client, status, fetch, tool_parameters, credentials.server_type, task_id or batch_id
        )

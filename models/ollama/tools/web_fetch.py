from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.client import call_ollama_cloud_api


class OllamaWebFetchTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        url = str(tool_parameters.get("url", "")).strip()
        if not url:
            yield self.create_text_message("Please input a URL to fetch.")
            return

        result = call_ollama_cloud_api(
            credentials=self.runtime.credentials,
            path="web_fetch",
            payload={"url": url},
        )

        yield self.create_json_message(result)
        yield self.create_text_message(self._format_fetch_result(result))

    @staticmethod
    def _format_fetch_result(result: dict[str, Any]) -> str:
        title = result.get("title") or ""
        content = result.get("content") or ""
        links = result.get("links") or []
        lines = [f"Title: {title}", "", content]
        if links:
            lines.extend(["", "Links:", *[str(link) for link in links]])
        return "\n".join(lines)

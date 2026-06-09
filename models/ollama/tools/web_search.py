from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.client import call_ollama_cloud_api


class OllamaWebSearchTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        query = str(tool_parameters.get("query", "")).strip()
        if not query:
            yield self.create_text_message("Please input a search query.")
            return

        max_results = int(tool_parameters.get("max_results") or 5)
        max_results = min(max(max_results, 1), 10)
        result = call_ollama_cloud_api(
            credentials=self.runtime.credentials,
            path="web_search",
            payload={"query": query, "max_results": max_results},
        )

        yield self.create_json_message(result)
        yield self.create_text_message(self._format_search_results(result))

    @staticmethod
    def _format_search_results(result: dict[str, Any]) -> str:
        results = result.get("results") or []
        if not results:
            return "No search results found."

        lines = ["Search results:"]
        for item in results:
            title = item.get("title", "")
            url = item.get("url", "")
            content = item.get("content", "")
            lines.extend(
                [
                    f"Title: {title}",
                    f"URL: {url}",
                    f"Content: {content}",
                    "---",
                ]
            )
        return "\n".join(lines)

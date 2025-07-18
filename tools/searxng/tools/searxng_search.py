from typing import Any, Generator
import requests
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class SearXNGSearchTool(Tool):
    """
    Tool for performing a search using SearXNG engine.
    """

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invoke the SearXNG search tool.

        Args:
            tool_parameters (dict[str, Any]): The parameters for the tool invocation.

        Returns:
            ToolInvokeMessage | list[ToolInvokeMessage]: The result of the tool invocation.
        """
        host = self.runtime.credentials.get("searxng_base_url")
        if not host:
            raise Exception("SearXNG api is required")
        response = requests.get(
            host,
            params={
                "q": tool_parameters.get("query"),
                "time_range": tool_parameters.get("time_range", "day"),
                "format": "json",
                "categories": tool_parameters.get("search_type", "general"),
            },
        )
        if response.status_code != 200:
            raise Exception(f"Error {response.status_code}: {response.text}")
        res = response.json().get("results", [])
        if not res:
            yield self.create_text_message(f"No results found, get response: {response.content}")
        else:
            for item in res:
                yield self.create_json_message(item)

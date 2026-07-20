from typing import Any, Generator
import requests
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool

SERPER_API_URL = "https://google.serper.dev/search"


class SerperSearchTool(Tool):
    def _parse_response(self, response: dict) -> dict:
        result = {}
        if "knowledgeGraph" in response:
            result["title"] = response["knowledgeGraph"].get("title", "")
            result["description"] = response["knowledgeGraph"].get("description", "")
        if "organic" in response:
            result["organic"] = [
                {"title": item.get("title", ""), "link": item.get("link", ""), "snippet": item.get("snippet", "")}
                for item in response["organic"]
            ]
        return result

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        serperapi_api_key = self.runtime.credentials.get("serperapi_api_key")
        if not serperapi_api_key:
            yield self.create_text_message("Serper.dev API key is required.")
            return

        params = {"q": tool_parameters["query"], "gl": "us", "hl": "en"}
        headers = {"X-API-KEY": serperapi_api_key, "Content-Type": "application/json"}
        try:
            response = requests.get(
                url=SERPER_API_URL, params=params, headers=headers, timeout=10
            )
            response.raise_for_status()
            valuable_res = self._parse_response(response.json())
        except requests.exceptions.RequestException as exc:
            yield self.create_text_message(
                f"An error occurred while invoking the tool: {exc}."
            )
            return
        yield self.create_json_message(valuable_res)

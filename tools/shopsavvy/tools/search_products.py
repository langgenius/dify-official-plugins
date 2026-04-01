from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class SearchProductsTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        api_key = self.runtime.credentials.get("shopsavvy_api_key")
        if not api_key:
            yield self.create_text_message("ShopSavvy API key is required.")
            return

        base_url = self.runtime.credentials.get("base_url", "").strip()
        if not base_url:
            base_url = "https://api.shopsavvy.com/v1"

        query = tool_parameters.get("query", "").strip()
        if not query:
            yield self.create_text_message("Search query is required.")
            return

        max_results = tool_parameters.get("max_results", 5)
        if isinstance(max_results, float):
            max_results = int(max_results)

        try:
            response = requests.get(
                f"{base_url}/products/search",
                params={"q": query, "limit": max_results},
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "User-Agent": "ShopSavvy-Dify/1.0",
                },
                timeout=30,
            )
        except requests.RequestException as e:
            yield self.create_text_message(f"Request failed: {str(e)}")
            return

        if not response.ok:
            yield self.create_text_message(
                f"ShopSavvy API error {response.status_code}: {response.text}"
            )
            return

        yield self.create_json_message(response.json())

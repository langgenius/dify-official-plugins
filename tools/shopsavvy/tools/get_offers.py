from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class GetOffersTool(Tool):
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

        identifier = tool_parameters.get("identifier", "").strip()
        if not identifier:
            yield self.create_text_message("Product identifier is required.")
            return

        params: dict[str, str] = {"ids": identifier}

        retailer = tool_parameters.get("retailer", "").strip()
        if retailer:
            params["retailer"] = retailer

        try:
            response = requests.get(
                f"{base_url}/products/offers",
                params=params,
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

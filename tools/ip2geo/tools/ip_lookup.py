import json
from typing import Any, Generator
import requests
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool

API_BASE_URL = "https://api.ip2geo.dev"


class Ip2GeoLookupTool(Tool):
    """Tool for looking up geolocation data from an IP address using ip2geo."""

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        ip_address = tool_parameters.get("ip_address", "")
        api_key = self.runtime.credentials["ip2geo_api_key"]

        if not ip_address:
            yield self.create_text_message("Please provide an IP address")
            return

        try:
            response = requests.get(
                f"{API_BASE_URL}/convert",
                params={"ip": ip_address},
                headers={"X-Api-Key": api_key},
                timeout=10,
            )

            if not response.ok:
                yield self.create_text_message(
                    f"ip2geo API error: HTTP {response.status_code}"
                )
                return

            data = response.json()

            if not data.get("success"):
                yield self.create_text_message(
                    f"ip2geo error: {data.get('message', 'Unknown error')}"
                )
                return

            yield self.create_text_message(
                text=json.dumps(data.get("data", {}), indent=2)
            )
        except requests.RequestException as e:
            yield self.create_text_message(
                f"Error performing IP lookup: {str(e)}"
            )

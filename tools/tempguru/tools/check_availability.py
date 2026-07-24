from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

API_BASE = "https://mcp.tempguru.co/api/v1"
USER_AGENT = "tempguru-dify-plugin/0.0.1"


class CheckAvailabilityTool(Tool):
    """Lead-time guidance for staffing an event in a city on a date."""

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        city = tool_parameters.get("city")
        date = tool_parameters.get("date")
        if not city or not date:
            yield self.create_text_message(
                "Both 'city' and 'date' parameters are required."
            )
            return

        params: dict[str, Any] = {"city": city, "date": date}
        if tool_parameters.get("role"):
            params["role"] = tool_parameters["role"]
        if tool_parameters.get("count"):
            params["count"] = tool_parameters["count"]

        try:
            response = requests.get(
                f"{API_BASE}/availability",
                params=params,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=30,
            )
            response.raise_for_status()
            yield self.create_json_message(response.json())
        except requests.RequestException as e:
            yield self.create_text_message(f"API request failed: {str(e)}")
        except ValueError:
            yield self.create_text_message("Failed to parse response from TempGuru API.")

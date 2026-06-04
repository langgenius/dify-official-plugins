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
        params: dict[str, Any] = {
            "city": tool_parameters["city"],
            "date": tool_parameters["date"],
        }
        if tool_parameters.get("role"):
            params["role"] = tool_parameters["role"]
        if tool_parameters.get("count"):
            params["count"] = tool_parameters["count"]

        response = requests.get(
            f"{API_BASE}/availability",
            params=params,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        yield self.create_json_message(response.json())

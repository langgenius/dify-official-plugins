from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

API_BASE = "https://mcp.tempguru.co/api/v1"
USER_AGENT = "tempguru-dify-plugin/0.0.1"


class GetRolePricingTool(Tool):
    """All-inclusive hourly rate range for a role in a city."""

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        params = {
            "role": tool_parameters["role"],
            "city": tool_parameters["city"],
        }
        response = requests.get(
            f"{API_BASE}/pricing",
            params=params,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        yield self.create_json_message(response.json())

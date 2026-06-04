from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

API_BASE = "https://mcp.tempguru.co/api/v1"
USER_AGENT = "tempguru-dify-plugin/0.0.1"


class GetComplianceByStateTool(Tool):
    """State-level minimum wage, overtime rules, and event-staffing compliance summary."""

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        params = {"state": tool_parameters["state"]}
        response = requests.get(
            f"{API_BASE}/compliance",
            params=params,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        yield self.create_json_message(response.json())

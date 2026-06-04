from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

API_BASE = "https://mcp.tempguru.co/api/v1"
USER_AGENT = "tempguru-dify-plugin/0.0.1"


class GetCitiesTool(Tool):
    """List cities TempGuru staffs, with tier classification."""

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        params: dict[str, Any] = {}
        if tool_parameters.get("state"):
            params["state"] = tool_parameters["state"]
        if tool_parameters.get("tier"):
            params["tier"] = tool_parameters["tier"]

        response = requests.get(
            f"{API_BASE}/cities",
            params=params,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=30,
        )
        response.raise_for_status()
        yield self.create_json_message(response.json())

from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool

from .firecrawl_appx import FirecrawlApp


class MonitorChecksTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        List historical checks for a monitor, or fetch the monitor itself.
        Docs: https://docs.firecrawl.dev/features/monitors
        """
        app = FirecrawlApp(
            api_key=self.runtime.credentials.get("firecrawl_api_key"), base_url=self.runtime.credentials.get("base_url")
        )
        monitor_id = tool_parameters["monitor_id"]
        operation = tool_parameters.get("operation", "checks")
        if operation == "checks":
            query = {
                "limit": tool_parameters.get("limit"),
                "offset": tool_parameters.get("offset"),
                "status": tool_parameters.get("status"),
            }
            query = {k: v for (k, v) in query.items() if v not in (None, "")}
            result = app.get_monitor_checks(monitor_id, **query)
        elif operation == "get":
            result = app.get_monitor(monitor_id)
        else:
            raise ValueError(f"Invalid operation: {operation}")
        yield self.create_json_message(result)

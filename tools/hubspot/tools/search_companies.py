from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from hubspot_client import HubSpotClient, HubSpotError


class SearchCompaniesTool(Tool):
    """Search / list companies with optional query, filter and sort."""

    OBJECT = "companies"

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        token = self.runtime.credentials.get("access_token")
        if not token:
            yield self.create_text_message("HubSpot access token is required.")
            return

        properties = tool_parameters.get("properties")
        prop_list = [p.strip() for p in properties.split(",") if p.strip()] if properties else None

        try:
            limit = int(tool_parameters.get("limit") or 20)
        except (TypeError, ValueError):
            limit = 20

        try:
            result = HubSpotClient(token).search(
                self.OBJECT,
                query=(tool_parameters.get("query") or "").strip() or None,
                filter_property=(tool_parameters.get("filter_property") or "").strip() or None,
                filter_operator=tool_parameters.get("filter_operator") or "EQ",
                filter_value=tool_parameters.get("filter_value"),
                sort_by=(tool_parameters.get("sort_by") or "").strip() or None,
                sort_direction=tool_parameters.get("sort_direction") or "DESCENDING",
                properties=prop_list,
                limit=limit,
                after=(tool_parameters.get("after") or "").strip() or None,
            )
        except HubSpotError as e:
            yield self.create_text_message(f"HubSpot error: {e.message}")
            return

        results = result.get("results", [])
        total = result.get("total")
        yield self.create_text_message(
            f"Found {len(results)} {self.OBJECT}" + (f" (total {total})." if total is not None else ".")
        )
        yield self.create_json_message(result)

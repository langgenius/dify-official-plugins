from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from hubspot_client import HubSpotClient, HubSpotError


class GetFormTool(Tool):
    """Get a HubSpot form definition (fields) by id."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        token = self.runtime.credentials.get("access_token")
        if not token:
            yield self.create_text_message("HubSpot access token is required.")
            return

        form_id = tool_parameters.get("form_id")
        if not form_id:
            yield self.create_text_message("'form_id' is required.")
            return

        try:
            result = HubSpotClient(token).get_form(form_id)
        except HubSpotError as e:
            yield self.create_text_message(f"HubSpot error: {e.message}")
            return

        yield self.create_text_message(f"Form retrieved (id: {result.get('id', form_id)}).")
        yield self.create_json_message(result)

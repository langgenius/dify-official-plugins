from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from hubspot_client import HubSpotClient, HubSpotError


class DeleteContactTool(Tool):
    """Delete a contact in HubSpot."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        token = self.runtime.credentials.get("access_token")
        if not token:
            yield self.create_text_message("HubSpot access token is required.")
            return

        contact_id = tool_parameters.get("contact_id")
        if not contact_id:
            yield self.create_text_message("'contact_id' is required.")
            return

        try:
            result = HubSpotClient(token).delete("contacts", contact_id)
        except HubSpotError as e:
            yield self.create_text_message(f"HubSpot error: {e.message}")
            return

        yield self.create_text_message(f"Contact deleted (id: {contact_id}).")
        yield self.create_json_message(result)

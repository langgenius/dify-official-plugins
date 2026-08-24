from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from hubspot_client import HubSpotClient, HubSpotError


class AddContactToListTool(Tool):
    """Add one or more contacts to a HubSpot contact list."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        token = self.runtime.credentials.get("access_token")
        if not token:
            yield self.create_text_message("HubSpot access token is required.")
            return

        list_id = tool_parameters.get("list_id")
        if not list_id:
            yield self.create_text_message("'list_id' is required.")
            return

        contact_ids = tool_parameters.get("contact_ids")
        if not contact_ids:
            yield self.create_text_message("'contact_ids' is required.")
            return
        record_ids = [c.strip() for c in str(contact_ids).split(",") if c.strip()]
        if not record_ids:
            yield self.create_text_message("Provide at least one contact id.")
            return

        try:
            result = HubSpotClient(token).add_to_list(list_id, record_ids)
        except HubSpotError as e:
            yield self.create_text_message(f"HubSpot error: {e.message}")
            return

        yield self.create_text_message(f"Added {len(record_ids)} contact(s) to list {list_id}.")
        yield self.create_json_message(result)

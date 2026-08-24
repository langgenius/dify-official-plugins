from collections.abc import Generator
from typing import Any
import json

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from hubspot_client import HubSpotClient, HubSpotError


class UpdateContactTool(Tool):
    """Update a contact in HubSpot."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        token = self.runtime.credentials.get("access_token")
        if not token:
            yield self.create_text_message("HubSpot access token is required.")
            return

        contact_id = tool_parameters.get("contact_id")
        if not contact_id:
            yield self.create_text_message("'contact_id' is required.")
            return

        properties: dict[str, Any] = {}
        for key in ("email", "firstname", "lastname", "phone", "company"):
            value = tool_parameters.get(key)
            if value:
                properties[key] = value

        extra = tool_parameters.get("properties")
        if extra:
            try:
                properties.update(json.loads(extra) if isinstance(extra, str) else extra)
            except Exception:
                yield self.create_text_message("'properties' must be a valid JSON object.")
                return

        if not properties:
            yield self.create_text_message("Provide at least one property to update (e.g. email).")
            return

        try:
            result = HubSpotClient(token).update("contacts", contact_id, properties)
        except HubSpotError as e:
            yield self.create_text_message(f"HubSpot error: {e.message}")
            return

        yield self.create_text_message(f"Contact updated (id: {result.get('id')}).")
        yield self.create_json_message(result)

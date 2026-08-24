from collections.abc import Generator
from typing import Any
import json

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from hubspot_client import HubSpotClient, HubSpotError


class UpdateTicketTool(Tool):
    """Update a ticket in HubSpot."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        token = self.runtime.credentials.get("access_token")
        if not token:
            yield self.create_text_message("HubSpot access token is required.")
            return

        ticket_id = (tool_parameters.get("ticket_id") or "").strip()
        if not ticket_id:
            yield self.create_text_message("A ticket_id is required.")
            return

        properties: dict[str, Any] = {}
        for key in ("subject", "content", "hs_pipeline", "hs_pipeline_stage", "hs_ticket_priority"):
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
            yield self.create_text_message("Provide at least one property to update.")
            return

        try:
            result = HubSpotClient(token).update("tickets", ticket_id, properties)
        except HubSpotError as e:
            yield self.create_text_message(f"HubSpot error: {e.message}")
            return

        yield self.create_text_message(f"Ticket updated (id: {result.get('id')}).")
        yield self.create_json_message(result)

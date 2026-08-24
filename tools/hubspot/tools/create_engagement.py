from collections.abc import Generator
from typing import Any
import json

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from hubspot_client import HubSpotClient, HubSpotError


class CreateEngagementTool(Tool):
    """Create an engagement (note, task, meeting, call, or email) in HubSpot."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        token = self.runtime.credentials.get("access_token")
        if not token:
            yield self.create_text_message("HubSpot access token is required.")
            return

        engagement_type = tool_parameters.get("engagement_type") or "notes"

        extra = tool_parameters.get("properties")
        if not extra:
            yield self.create_text_message("'properties' is required.")
            return
        try:
            properties = json.loads(extra) if isinstance(extra, str) else extra
        except Exception:
            yield self.create_text_message("'properties' must be a valid JSON object.")
            return
        if not isinstance(properties, dict) or not properties:
            yield self.create_text_message("'properties' must be a non-empty JSON object.")
            return

        try:
            result = HubSpotClient(token).create(engagement_type, properties)
        except HubSpotError as e:
            yield self.create_text_message(f"HubSpot error: {e.message}")
            return

        yield self.create_text_message(f"Engagement created (id: {result.get('id')}).")
        yield self.create_json_message(result)

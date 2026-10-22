from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.graph_client import GraphAuthError, resolve_graph_context


class DeleteEventTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Delete a calendar event in Outlook using Microsoft Graph API
        """
        try:
            event_id = tool_parameters.get("event_id", "")

            if not event_id:
                yield self.create_text_message("Event ID is required.")
                return

            try:
                graph = resolve_graph_context(self.runtime.credentials, tool_parameters.get("mailbox"))
            except GraphAuthError as e:
                yield self.create_text_message(str(e))
                return
            access_token = graph.access_token
            self._mailbox_base = graph.mailbox_base

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            url = f"{self._mailbox_base}/events/{event_id}"

            try:
                response = requests.delete(url, headers=headers, timeout=30)
            except requests.exceptions.RequestException as e:
                yield self.create_text_message(f"Network error: {str(e)}")
                return

            if response.status_code != 204:
                yield self.create_text_message(
                    f"API error {response.status_code}: {response.text}"
                )
                return

            yield self.create_text_message(f"Event {event_id} deleted successfully.")
            yield self.create_json_message({"status": "deleted", "event_id": event_id})

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

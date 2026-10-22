from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.graph_client import GraphAuthError, resolve_graph_context


class ListCalendarsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        List the user's Outlook calendars using Microsoft Graph API
        """
        try:
            top = tool_parameters.get("top") or 50

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

            url = f"{self._mailbox_base}/calendars"
            params = {"$top": int(top)}

            try:
                response = requests.get(url, headers=headers, params=params, timeout=30)
            except requests.exceptions.RequestException as e:
                yield self.create_text_message(f"Network error: {str(e)}")
                return

            if response.status_code < 200 or response.status_code >= 300:
                yield self.create_text_message(
                    f"API error {response.status_code}: {response.text}"
                )
                return

            data = response.json()
            calendars = data.get("value", [])
            summary = "\n".join(
                f"- {c.get('name')} (id: {c.get('id')})" for c in calendars
            )
            yield self.create_text_message(
                f"Found {len(calendars)} calendar(s):\n{summary}" if calendars else "No calendars found."
            )
            yield self.create_json_message(data)

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.graph_client import GraphAuthError, resolve_graph_context


class ListEventsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        List calendar events from Outlook using Microsoft Graph API
        """
        try:
            limit = tool_parameters.get("limit") or 25
            calendar_id = tool_parameters.get("calendar_id")

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

            if calendar_id:
                url = f"{self._mailbox_base}/calendars/{calendar_id}/events"
            else:
                url = f"{self._mailbox_base}/events"

            params = {
                "$top": int(limit),
                "$orderby": "start/dateTime desc",
                "$select": "id,subject,start,end,organizer,webLink"
            }

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
            events = data.get("value", [])
            lines = []
            for e in events:
                start = (e.get("start") or {}).get("dateTime")
                end = (e.get("end") or {}).get("dateTime")
                lines.append(f"- {e.get('subject')} [{start} - {end}] (id: {e.get('id')})")
            summary = "\n".join(lines)
            yield self.create_text_message(
                f"Found {len(events)} event(s):\n{summary}" if events else "No events found."
            )
            yield self.create_json_message(data)

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class GetEventTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Get a single calendar event from Outlook using Microsoft Graph API
        """
        try:
            event_id = tool_parameters.get("event_id", "")

            if not event_id:
                yield self.create_text_message("Event ID is required.")
                return

            access_token = self.runtime.credentials.get("access_token")
            if not access_token:
                yield self.create_text_message("Access token is required in credentials.")
                return

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            url = f"https://graph.microsoft.com/v1.0/me/events/{event_id}"

            try:
                response = requests.get(url, headers=headers, timeout=30)
            except requests.exceptions.RequestException as e:
                yield self.create_text_message(f"Network error: {str(e)}")
                return

            if response.status_code < 200 or response.status_code >= 300:
                yield self.create_text_message(
                    f"API error {response.status_code}: {response.text}"
                )
                return

            data = response.json()
            start = (data.get("start") or {}).get("dateTime")
            end = (data.get("end") or {}).get("dateTime")
            yield self.create_text_message(
                f"Event: {data.get('subject')} [{start} - {end}] (id: {data.get('id')})"
            )
            yield self.create_json_message(data)

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

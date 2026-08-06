from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class UpdateEventTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Update a calendar event in Outlook using Microsoft Graph API
        """
        try:
            event_id = tool_parameters.get("event_id", "")
            subject = tool_parameters.get("subject")
            start_datetime = tool_parameters.get("start_datetime")
            end_datetime = tool_parameters.get("end_datetime")
            time_zone = tool_parameters.get("time_zone") or "UTC"
            body = tool_parameters.get("body")
            location = tool_parameters.get("location")

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

            patch_body: dict[str, Any] = {}
            if subject:
                patch_body["subject"] = subject
            if start_datetime:
                patch_body["start"] = {"dateTime": start_datetime, "timeZone": time_zone}
            if end_datetime:
                patch_body["end"] = {"dateTime": end_datetime, "timeZone": time_zone}
            if body:
                patch_body["body"] = {"contentType": "HTML", "content": body}
            if location:
                patch_body["location"] = {"displayName": location}

            if not patch_body:
                yield self.create_text_message("No fields provided to update.")
                return

            url = f"https://graph.microsoft.com/v1.0/me/events/{event_id}"

            try:
                response = requests.patch(url, headers=headers, json=patch_body, timeout=30)
            except requests.exceptions.RequestException as e:
                yield self.create_text_message(f"Network error: {str(e)}")
                return

            if response.status_code < 200 or response.status_code >= 300:
                yield self.create_text_message(
                    f"API error {response.status_code}: {response.text}"
                )
                return

            data = response.json()
            yield self.create_text_message(
                f"Event updated: {data.get('subject')} (id: {data.get('id')})"
            )
            yield self.create_json_message(data)

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

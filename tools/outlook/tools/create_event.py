from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class CreateEventTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Create a calendar event in Outlook using Microsoft Graph API
        """
        try:
            subject = tool_parameters.get("subject", "")
            start_datetime = tool_parameters.get("start_datetime", "")
            end_datetime = tool_parameters.get("end_datetime", "")
            time_zone = tool_parameters.get("time_zone") or "UTC"
            body = tool_parameters.get("body")
            attendees = tool_parameters.get("attendees")
            location = tool_parameters.get("location")
            is_online_meeting = tool_parameters.get("is_online_meeting", False)

            if not subject:
                yield self.create_text_message("Subject is required.")
                return
            if not start_datetime:
                yield self.create_text_message("Start datetime is required.")
                return
            if not end_datetime:
                yield self.create_text_message("End datetime is required.")
                return

            access_token = self.runtime.credentials.get("access_token")
            if not access_token:
                yield self.create_text_message("Access token is required in credentials.")
                return

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }

            event_body: dict[str, Any] = {
                "subject": subject,
                "start": {"dateTime": start_datetime, "timeZone": time_zone},
                "end": {"dateTime": end_datetime, "timeZone": time_zone},
            }

            if body:
                event_body["body"] = {"contentType": "HTML", "content": body}

            if location:
                event_body["location"] = {"displayName": location}

            if attendees:
                attendee_list = [a.strip() for a in attendees.split(",") if a.strip()]
                if attendee_list:
                    event_body["attendees"] = [
                        {"emailAddress": {"address": addr}, "type": "required"}
                        for addr in attendee_list
                    ]

            if is_online_meeting:
                event_body["isOnlineMeeting"] = True
                event_body["onlineMeetingProvider"] = "teamsForBusiness"

            url = "https://graph.microsoft.com/v1.0/me/events"

            try:
                response = requests.post(url, headers=headers, json=event_body, timeout=30)
            except requests.exceptions.RequestException as e:
                yield self.create_text_message(f"Network error: {str(e)}")
                return

            if response.status_code < 200 or response.status_code >= 300:
                yield self.create_text_message(
                    f"API error {response.status_code}: {response.text}"
                )
                return

            data = response.json()
            join_url = (data.get("onlineMeeting") or {}).get("joinUrl")
            message = f"Event created: {data.get('subject')} (id: {data.get('id')})"
            if data.get("webLink"):
                message += f"\nWeb link: {data.get('webLink')}"
            if join_url:
                message += f"\nJoin URL: {join_url}"
            yield self.create_text_message(message)
            yield self.create_json_message(data)

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

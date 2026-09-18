from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ListGroupCalendarEventsTool(Tool):
    """List events from the Microsoft 365 group calendar backing a Team.

    A Microsoft Teams team is backed by a Microsoft 365 group; that group has a
    calendar. With a start/end range this uses the Graph calendarView endpoint
    (which also expands recurring events into single instances); without a range
    it lists the group's events. Requires the Group.Read.All permission.
    """

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        access_token = self.runtime.credentials.get("access_token")
        if not access_token:
            yield self.create_text_message("Access token is required in credentials.")
            return

        team_id = (tool_parameters.get("team_id") or "").strip()
        if not team_id:
            yield self.create_text_message("team_id is required.")
            return

        start_datetime = (tool_parameters.get("start_datetime") or "").strip()
        end_datetime = (tool_parameters.get("end_datetime") or "").strip()
        if bool(start_datetime) != bool(end_datetime):
            yield self.create_text_message(
                "Provide both start_datetime and end_datetime for a date range, or neither."
            )
            return

        try:
            top = int(tool_parameters.get("top") or 20)
        except (TypeError, ValueError):
            top = 20

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        select = "id,subject,start,end,organizer,attendees,onlineMeeting,isOnlineMeeting,location,webLink"

        # calendarView needs a range and expands recurring events; /events lists as-is.
        if start_datetime and end_datetime:
            url = f"https://graph.microsoft.com/v1.0/groups/{team_id}/calendarView"
            params = {
                "startDateTime": start_datetime,
                "endDateTime": end_datetime,
                "$top": top,
                "$orderby": "start/dateTime",
                "$select": select,
            }
        else:
            url = f"https://graph.microsoft.com/v1.0/groups/{team_id}/events"
            params = {
                "$top": top,
                "$orderby": "start/dateTime",
                "$select": select,
            }

        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(f"Network error: {str(e)}")
            return

        if response.status_code == 403:
            yield self.create_text_message(
                "Access denied (403). The group calendar needs the Group.Read.All "
                "permission - re-authorize and make sure your Azure admin has consented to it."
            )
            return
        if response.status_code < 200 or response.status_code >= 300:
            yield self.create_text_message(f"API error {response.status_code}: {response.text}")
            return

        data = response.json()
        events = [
            {
                "id": e.get("id"),
                "subject": e.get("subject"),
                "start": e.get("start"),
                "end": e.get("end"),
                "organizer": e.get("organizer"),
                "attendees": e.get("attendees"),
                "location": e.get("location"),
                "is_online_meeting": e.get("isOnlineMeeting"),
                "online_meeting": e.get("onlineMeeting"),
                "web_link": e.get("webLink"),
            }
            for e in data.get("value", [])
        ]

        if not events:
            yield self.create_text_message("No events found in the group calendar.")
        else:
            lines = [
                f"- {ev['subject']} [{(ev['start'] or {}).get('dateTime')} - {(ev['end'] or {}).get('dateTime')}] (id: {ev['id']})"
                for ev in events
            ]
            yield self.create_text_message(
                f"Found {len(events)} event(s):\n" + "\n".join(lines)
            )

        yield self.create_json_message({"events": events})

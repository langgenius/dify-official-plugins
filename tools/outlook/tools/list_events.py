from collections.abc import Generator
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.graph_client import calendar_tag, calendars_in_group, describe_error, event_vars, GraphAuthError, resolve_graph_context, segment
from tools.outputs import with_outputs


class ListEventsTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        List calendar events from Outlook using Microsoft Graph API: from the default
        calendar, one calendar, or every calendar in a calendar group (merged).
        """
        try:
            limit = tool_parameters.get("limit") or 25
            calendar_id = (tool_parameters.get("calendar_id") or "").strip()
            calendar_group_id = (tool_parameters.get("calendar_group_id") or "").strip()

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

            params = {
                "$top": int(limit),
                "$orderby": "start/dateTime desc",
                "$select": "id,subject,start,end,organizer,webLink"
            }

            if calendar_group_id and not calendar_id:
                yield from self._list_group(graph, calendar_group_id, headers, params, int(limit))
                return

            if calendar_id:
                url = f"{self._mailbox_base}/calendars/{segment(calendar_id)}/events"
            else:
                url = f"{self._mailbox_base}/events"

            try:
                response = requests.get(url, headers=headers, params=params, timeout=30)
            except requests.exceptions.RequestException as e:
                yield self.create_text_message(f"Network error: {str(e)}")
                return

            if response.status_code < 200 or response.status_code >= 300:
                yield self.create_text_message(describe_error(response))
                return

            data = response.json()
            events = data.get("value", [])
            self._out.update(events=[event_vars(e) for e in events], count=len(events), success=True)
            yield self.create_text_message(self._summary(events))
            yield self.create_json_message(data)

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

    def _list_group(self, graph, group_id: str, headers: dict, params: dict, limit: int):
        """Events of every calendar in the group, each tagged with its calendar and owner, newest first."""
        try:
            calendars = calendars_in_group(graph, group_id)
        except GraphAuthError as e:
            yield self.create_text_message(str(e))
            return
        if not calendars:
            yield self.create_text_message("This calendar group has no calendars.")
            return

        events: list[dict] = []
        errors: list[dict] = []
        for calendar in calendars:
            url = f"{graph.mailbox_base}/calendars/{segment(calendar.get('id'))}/events"
            try:
                response = requests.get(url, headers=headers, params=params, timeout=30)
            except requests.exceptions.RequestException as e:
                errors.append({"calendar": calendar_tag(calendar), "error": f"Network error: {e}"})
                continue
            if response.status_code < 200 or response.status_code >= 300:
                # One unreadable shared calendar must not hide the others.
                errors.append({"calendar": calendar_tag(calendar), "error": describe_error(response)})
                continue
            for event in response.json().get("value", []):
                event["calendar"] = calendar_tag(calendar)
                events.append(event)

        events.sort(key=lambda e: (e.get("start") or {}).get("dateTime") or "", reverse=True)
        events = events[:limit]
        self._out.update(
            events=[event_vars(e) for e in events], count=len(events),
            errors=[{"calendar_name": e["calendar"]["name"] or "", "error": e["error"]} for e in errors], success=True,
        )
        text = self._summary(events)
        if errors:
            text += f"\n{len(errors)} calendar(s) could not be read: " + "; ".join(
                f"{e['calendar']['name']}: {e['error']}" for e in errors
            )
        yield self.create_text_message(text)
        yield self.create_json_message(
            {"calendar_group_id": group_id, "calendars": [calendar_tag(c) for c in calendars], "value": events, "errors": errors}
        )

    @staticmethod
    def _summary(events: list[dict]) -> str:
        if not events:
            return "No events found."
        lines = []
        for e in events:
            start = (e.get("start") or {}).get("dateTime")
            end = (e.get("end") or {}).get("dateTime")
            cal = e.get("calendar")
            where = f" — {cal.get('owner_name') or cal.get('name')}" if cal else ""
            lines.append(f"- {e.get('subject')} [{start} - {end}]{where} (id: {e.get('id')})")
        return f"Found {len(events)} event(s):\n" + "\n".join(lines)

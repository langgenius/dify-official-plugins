from collections.abc import Generator
from datetime import date, datetime, timezone
from typing import Any
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.graph_client import calendars_in_group, describe_error, GraphAuthError, resolve_graph_context
from tools.outputs import with_outputs

# getSchedule takes a bounded number of schedules per request; larger lists are sent in chunks.
_CHUNK = 20
_STATUS = {"0": "free", "1": "tentative", "2": "busy", "3": "oof", "4": "workingElsewhere"}


class GetScheduleTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Free/busy of one or more people for a time window (Microsoft Graph getSchedule).

        Works for anyone in the organisation without their calendar being shared: Exchange
        returns free/busy by default, and subjects/locations only where the caller may see them.
        People can be given as email addresses and/or as a calendar group, whose calendars'
        owners are used (e.g. the executives' calendars in "People's calendars").
        """
        try:
            emails = [e.strip() for e in str(tool_parameters.get("emails") or "").replace("\n", ",").split(",") if e.strip()]
            calendar_group_id = (tool_parameters.get("calendar_group_id") or "").strip()
            start_value = (tool_parameters.get("start_datetime") or "").strip()
            end_value = (tool_parameters.get("end_datetime") or "").strip()
            time_zone = (tool_parameters.get("time_zone") or "UTC").strip()
            try:
                interval = int(tool_parameters.get("interval_minutes") or 30)
            except (TypeError, ValueError):
                interval = 30

            if not start_value or not end_value:
                yield self.create_text_message("start_datetime and end_datetime are required.")
                return
            if not 5 <= interval <= 1440:
                yield self.create_text_message("interval_minutes must be between 5 and 1440.")
                return
            try:
                start = self._graph_time(start_value, time_zone, end_of_day=False)
                end = self._graph_time(end_value, time_zone, end_of_day=True)
            except ValueError:
                yield self.create_text_message(
                    "start_datetime and end_datetime must be ISO 8601, e.g. 2026-12-01T09:00:00 or 2026-12-01T09:00:00+09:00."
                )
                return

            try:
                graph = resolve_graph_context(self.runtime.credentials, tool_parameters.get("mailbox"))
                if calendar_group_id:
                    for calendar in calendars_in_group(graph, calendar_group_id):
                        address = ((calendar.get("owner") or {}).get("address") or "").strip()
                        if address:
                            emails.append(address)
            except GraphAuthError as e:
                yield self.create_text_message(str(e))
                return

            # Keep the order, drop duplicates (case-insensitive).
            seen: set[str] = set()
            emails = [e for e in emails if not (e.lower() in seen or seen.add(e.lower()))]
            if not emails:
                yield self.create_text_message("Provide emails and/or a calendar_group_id whose calendars have owners.")
                return

            headers = {
                "Authorization": f"Bearer {graph.access_token}",
                "Content-Type": "application/json",
                # Return the busy slots in the caller's time zone.
                "Prefer": f'outlook.timezone="{time_zone}"',
            }
            schedules: list[dict] = []
            for i in range(0, len(emails), _CHUNK):
                body = {
                    "schedules": emails[i:i + _CHUNK],
                    "startTime": start,
                    "endTime": end,
                    "availabilityViewInterval": interval,
                }
                try:
                    response = requests.post(
                        f"{graph.mailbox_base}/calendar/getSchedule", headers=headers, json=body, timeout=30
                    )
                except requests.exceptions.RequestException as e:
                    yield self.create_text_message(f"Network error: {str(e)}")
                    return
                if response.status_code < 200 or response.status_code >= 300:
                    yield self.create_text_message(describe_error(response))
                    return
                schedules.extend(self._format(item) for item in response.json().get("value", []))

            self._out.update(
                schedules=[{"email": s["email"] or "", "availability_view": s["availability_view"], "availability": s["availability"],
                            "busy_count": len(s["busy"]), "error": s["error"] or ""} for s in schedules],
                busy_people=[s["email"] for s in schedules if s["busy"]],
                count=len(schedules), success=True,
            )
            lines = []
            for s in schedules:
                if s.get("error"):
                    lines.append(f"- {s['email']}: could not read ({s['error']})")
                elif not s["busy"]:
                    lines.append(f"- {s['email']}: free for the whole window")
                else:
                    slots = ", ".join(
                        f"{b['start'][5:16].replace('T', ' ')}-{b['end'][11:16]} {b['status']}" + (f" ({b['subject']})" if b.get("subject") else "")
                        for b in s["busy"]
                    )
                    lines.append(f"- {s['email']}: {slots}")
            yield self.create_text_message(
                f"Schedule {start['dateTime']} - {end['dateTime']} ({start['timeZone']}), times shown in {time_zone}:\n"
                + "\n".join(lines)
            )
            yield self.create_json_message(
                {"start": start, "end": end, "time_zone": time_zone, "interval_minutes": interval, "schedules": schedules}
            )

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

    @staticmethod
    def _graph_time(value: str, time_zone: str, end_of_day: bool) -> dict:
        """
        A dateTimeTimeZone for getSchedule. A value with a UTC offset is converted to UTC;
        a value without one is taken in ``time_zone``; a bare date covers the whole day.
        """
        if len(value) == 10:
            day = date.fromisoformat(value)
            return {"dateTime": f"{day.isoformat()}T{'23:59:59' if end_of_day else '00:00:00'}", "timeZone": time_zone}
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return {"dateTime": parsed.strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": time_zone}
        return {"dateTime": parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"), "timeZone": "UTC"}

    @staticmethod
    def _format(item: dict) -> dict:
        error = item.get("error")
        busy = [
            {
                "status": slot.get("status"),
                "start": (slot.get("start") or {}).get("dateTime") or "",
                "end": (slot.get("end") or {}).get("dateTime") or "",
                "subject": slot.get("subject"),
                "location": slot.get("location"),
            }
            for slot in item.get("scheduleItems") or []
            if slot.get("status") != "free"
        ]
        view = item.get("availabilityView") or ""
        return {
            "email": item.get("scheduleId"),
            "availability_view": view,
            "availability": [_STATUS.get(ch, ch) for ch in view],
            "busy": busy,
            "working_hours": item.get("workingHours"),
            "error": (error or {}).get("message") if error else None,
        }

from collections.abc import Generator
from typing import Any
from datetime import datetime, timedelta, timezone
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

GRAPH = "https://graph.microsoft.com/v1.0"
SELECT = "id,subject,start,end,organizer,location,webLink,bodyPreview"


class SearchEventsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Search calendar events by keyword and/or date range via Microsoft Graph.

        - Date range given  -> calendarView(start, end), ordered by start time.
        - Keyword only       -> /me/events?$search="query".
        - Both               -> calendarView for the range, then keyword-filtered
          client-side (Graph cannot combine $search with a date filter).
        """
        try:
            query = (tool_parameters.get("query") or "").strip()
            start_date = (tool_parameters.get("start_date") or "").strip()
            end_date = (tool_parameters.get("end_date") or "").strip()
            calendar_id = (tool_parameters.get("calendar_id") or "").strip()
            try:
                limit = int(tool_parameters.get("limit") or 25)
            except (TypeError, ValueError):
                limit = 25
            if limit < 1 or limit > 100:
                yield self.create_text_message("Limit must be between 1 and 100.")
                return

            if not query and not start_date and not end_date:
                yield self.create_text_message(
                    "Provide a keyword (query) and/or a date range (start_date/end_date) to search events."
                )
                return

            access_token = self.runtime.credentials.get("access_token")
            if not access_token:
                yield self.create_text_message("Access token is required in credentials.")
                return

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            use_range = bool(start_date or end_date)
            if use_range:
                start_iso = self._to_iso(start_date, end_of_day=False) or self._now_iso()
                end_iso = self._to_iso(end_date, end_of_day=True) or self._plus_days_iso(start_iso, 365)
                base = (
                    f"{GRAPH}/me/calendars/{calendar_id}/calendarView"
                    if calendar_id else f"{GRAPH}/me/calendarView"
                )
                params = {
                    "startDateTime": start_iso,
                    "endDateTime": end_iso,
                    "$orderby": "start/dateTime",
                    # Fetch a full page when we still have to keyword-filter client-side.
                    "$top": 100 if query else limit,
                    "$select": SELECT,
                }
            else:
                base = f"{GRAPH}/me/calendars/{calendar_id}/events" if calendar_id else f"{GRAPH}/me/events"
                params = {
                    "$search": f'"{query}"',
                    "$top": limit,
                    "$select": SELECT,
                }
                headers["ConsistencyLevel"] = "eventual"  # required for $search

            try:
                resp = requests.get(base, headers=headers, params=params, timeout=30)
            except requests.exceptions.RequestException as e:
                yield self.create_text_message(f"Network error: {str(e)}")
                return

            if resp.status_code == 401:
                yield self.create_text_message("Authentication failed. Token may be expired.")
                return
            if resp.status_code == 403:
                yield self.create_text_message("Access denied. Check calendar permissions and admin consent.")
                return
            if resp.status_code < 200 or resp.status_code >= 300:
                yield self.create_text_message(f"API error {resp.status_code}: {resp.text}")
                return

            events = resp.json().get("value", [])

            # Graph can't combine $search with a date range, so when both are given
            # we pull the range from calendarView and filter by keyword here.
            if use_range and query:
                q = query.lower()
                events = [
                    e for e in events
                    if q in (e.get("subject") or "").lower()
                    or q in (e.get("bodyPreview") or "").lower()
                ][:limit]

            if not events:
                yield self.create_text_message("No matching events found.")
                return

            lines = []
            for e in events:
                start = (e.get("start") or {}).get("dateTime")
                end = (e.get("end") or {}).get("dateTime")
                lines.append(f"- {e.get('subject')} [{start} - {end}] (id: {e.get('id')})")
            yield self.create_text_message(f"Found {len(events)} event(s):\n" + "\n".join(lines))
            yield self.create_json_message({"total_count": len(events), "events": events})

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _to_iso(value: str, end_of_day: bool) -> str:
        """Normalize a user date/datetime into an ISO 8601 string Graph accepts."""
        v = (value or "").strip()
        if not v:
            return ""
        if "T" not in v:  # date only, e.g. 2026-09-01
            return v + ("T23:59:59Z" if end_of_day else "T00:00:00Z")
        if v.endswith("Z") or "+" in v:
            return v
        return v + "Z"

    @staticmethod
    def _plus_days_iso(start_iso: str, days: int) -> str:
        try:
            base = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        except Exception:
            base = datetime.now(timezone.utc)
        return (base + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

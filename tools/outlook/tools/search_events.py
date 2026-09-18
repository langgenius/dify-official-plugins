from collections.abc import Generator
from typing import Any, Optional
from datetime import datetime, timedelta, timezone
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

GRAPH = "https://graph.microsoft.com/v1.0"
SELECT = "id,subject,start,end,organizer,location,webLink,bodyPreview"
_MAX_PAGES = 25  # safety cap when following @odata.nextLink


class SearchEventsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Search calendar events by keyword and/or date range via Microsoft Graph.

        - Date range given  -> calendarView(start, end), ordered by start time,
          following @odata.nextLink across pages.
        - Keyword only       -> /me/events?$search="query".
        - Both               -> calendarView for the range, keyword-filtered
          client-side (Graph cannot combine $search with a date filter), paging
          until `limit` matches are found or the range is exhausted.
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

                start_dt, end_dt = self._parse(start_iso), self._parse(end_iso)
                if start_dt and end_dt and start_dt > end_dt:
                    yield self.create_text_message("start_date must be before end_date.")
                    return

                base = (
                    f"{GRAPH}/me/calendars/{calendar_id}/calendarView"
                    if calendar_id else f"{GRAPH}/me/calendarView"
                )
                params: Optional[dict] = {
                    "startDateTime": start_iso,
                    "endDateTime": end_iso,
                    "$orderby": "start/dateTime",
                    # Fetch full pages when we still have to keyword-filter client-side.
                    "$top": 100 if query else limit,
                    "$select": SELECT,
                }

                q = query.lower() if query else None
                events: list[dict] = []
                url: Optional[str] = base
                pages = 0
                # Follow @odata.nextLink until we have enough matches or run out.
                while url and len(events) < limit and pages < _MAX_PAGES:
                    try:
                        resp = requests.get(url, headers=headers, params=params, timeout=30)
                    except requests.exceptions.RequestException as e:
                        yield self.create_text_message(f"Network error: {str(e)}")
                        return
                    err = self._http_error(resp)
                    if err:
                        yield self.create_text_message(err)
                        return
                    body = resp.json()
                    page = body.get("value", [])
                    if q:
                        page = [
                            e for e in page
                            if q in (e.get("subject") or "").lower()
                            or q in (e.get("bodyPreview") or "").lower()
                        ]
                    events.extend(page)
                    url = body.get("@odata.nextLink")
                    params = None  # nextLink already carries the query string
                    pages += 1
                events = events[:limit]
            else:
                base = f"{GRAPH}/me/calendars/{calendar_id}/events" if calendar_id else f"{GRAPH}/me/events"
                headers["ConsistencyLevel"] = "eventual"  # required for $search
                params = {"$search": f'"{query}"', "$top": limit, "$select": SELECT}
                try:
                    resp = requests.get(base, headers=headers, params=params, timeout=30)
                except requests.exceptions.RequestException as e:
                    yield self.create_text_message(f"Network error: {str(e)}")
                    return
                err = self._http_error(resp)
                if err:
                    yield self.create_text_message(err)
                    return
                events = resp.json().get("value", [])[:limit]

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
    def _http_error(resp) -> Optional[str]:
        if resp.status_code == 401:
            return "Authentication failed. Token may be expired."
        if resp.status_code == 403:
            return "Access denied. Check calendar permissions and admin consent."
        if resp.status_code < 200 or resp.status_code >= 300:
            return f"API error {resp.status_code}: {resp.text}"
        return None

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _to_iso(value: str, end_of_day: bool) -> str:
        """Normalize a user date/datetime into an ISO 8601 string Graph accepts.

        Preserves an existing timezone offset (Z, +HH:MM or -HH:MM) instead of
        blindly appending 'Z' (which would corrupt an offset like -05:00).
        """
        v = (value or "").strip()
        if not v:
            return ""
        if "T" not in v:  # date only, e.g. 2026-09-01
            return v + ("T23:59:59Z" if end_of_day else "T00:00:00Z")
        timepart = v.split("T", 1)[1]
        if timepart.endswith("Z") or "+" in timepart or "-" in timepart:
            return v  # already carries an offset
        return v + "Z"

    @staticmethod
    def _parse(iso: str) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(iso.replace("Z", "+00:00"))
        except Exception:
            return None

    @staticmethod
    def _plus_days_iso(start_iso: str, days: int) -> str:
        base = SearchEventsTool._parse(start_iso) or datetime.now(timezone.utc)
        return (base + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

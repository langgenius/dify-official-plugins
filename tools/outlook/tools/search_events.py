from collections.abc import Generator
from typing import Any, Optional
from datetime import datetime, timedelta, timezone
import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from tools.graph_client import calendar_tag, calendars_in_group, describe_error, event_vars, GraphAuthError, resolve_graph_context, segment
from tools.outputs import with_outputs

SELECT = "id,subject,start,end,organizer,location,webLink,bodyPreview"
_MAX_PAGES = 25  # safety cap when following @odata.nextLink


class _SearchError(Exception):
    """A Graph error for one calendar; the message is shown to the user."""


class SearchEventsTool(Tool):
    @with_outputs
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Search calendar events by keyword and/or date range via Microsoft Graph, in the
        default calendar, one calendar, or every calendar of a calendar group (merged).
        How one calendar is searched is described in _search_one.
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

            try:
                graph = resolve_graph_context(self.runtime.credentials, tool_parameters.get("mailbox"))
            except GraphAuthError as e:
                yield self.create_text_message(str(e))
                return
            access_token = graph.access_token
            self._mailbox_base = graph.mailbox_base

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            use_range = bool(start_date or end_date)
            calendar_group_id = (tool_parameters.get("calendar_group_id") or "").strip()

            if use_range:
                start_iso = self._to_iso(start_date, end_of_day=False) or self._now_iso()
                end_iso = self._to_iso(end_date, end_of_day=True) or self._plus_days_iso(start_iso, 365)

                start_dt, end_dt = self._parse(start_iso), self._parse(end_iso)
                if start_dt and end_dt and start_dt > end_dt:
                    yield self.create_text_message("start_date must be before end_date.")
                    return
            else:
                start_iso = end_iso = ""

            # Where to search: the default calendar, one calendar, or every calendar in a group.
            calendars: list[Optional[dict]] = [None]
            if calendar_id:
                calendars = [{"id": calendar_id}]
            elif calendar_group_id:
                try:
                    calendars = calendars_in_group(graph, calendar_group_id)
                except GraphAuthError as e:
                    yield self.create_text_message(str(e))
                    return
                if not calendars:
                    yield self.create_text_message("This calendar group has no calendars.")
                    return

            events: list[dict] = []
            errors: list[dict] = []
            for calendar in calendars:
                base = f"{self._mailbox_base}/calendars/{segment(calendar['id'])}" if calendar else self._mailbox_base
                try:
                    found = self._search_one(base, dict(headers), query, start_iso, end_iso, limit, use_range)
                except requests.exceptions.RequestException as e:
                    message = f"Network error: {str(e)}"
                except _SearchError as e:
                    message = str(e)
                else:
                    if calendar_group_id and calendar:
                        for event in found:
                            event["calendar"] = calendar_tag(calendar)
                    events.extend(found)
                    continue
                if len(calendars) == 1:
                    yield self.create_text_message(message)
                    return
                # One unreadable shared calendar must not hide the others.
                errors.append({"calendar": calendar_tag(calendar), "error": message})

            if len(calendars) > 1:
                events.sort(key=lambda e: (e.get("start") or {}).get("dateTime") or "")
            events = events[:limit]

            failed = (
                f"\n{len(errors)} calendar(s) could not be read: "
                + "; ".join(f"{e['calendar']['name']}: {e['error']}" for e in errors)
                if errors else ""
            )
            self._out.update(
                events=[event_vars(e) for e in events], count=len(events),
                errors=[{"calendar_name": (e["calendar"] or {}).get("name") or "", "error": e["error"]} for e in errors], success=True,
            )
            if not events:
                yield self.create_text_message("No matching events found." + failed)
                if errors:
                    yield self.create_json_message({"total_count": 0, "events": [], "errors": errors})
                return

            lines = []
            for e in events:
                start = (e.get("start") or {}).get("dateTime")
                end = (e.get("end") or {}).get("dateTime")
                cal = e.get("calendar")
                where = f" — {cal.get('owner_name') or cal.get('name')}" if cal else ""
                lines.append(f"- {e.get('subject')} [{start} - {end}]{where} (id: {e.get('id')})")
            yield self.create_text_message(f"Found {len(events)} event(s):\n" + "\n".join(lines) + failed)
            result: dict[str, Any] = {"total_count": len(events), "events": events}
            if errors:
                result["errors"] = errors
            yield self.create_json_message(result)

        except Exception as e:
            yield self.create_text_message(f"Error: {str(e)}")
            return

    def _search_one(self, base: str, headers: dict, query: str, start_iso: str, end_iso: str, limit: int, use_range: bool) -> list[dict]:
        """
        Search one calendar root (``{mailbox}`` or ``{mailbox}/calendars/{id}``).

        - Date range given  -> calendarView(start, end), ordered by start time,
          following @odata.nextLink across pages.
        - Keyword only       -> events?$search="query".
        - Both               -> calendarView for the range, keyword-filtered
          client-side (Graph cannot combine $search with a date filter), paging
          until `limit` matches are found or the range is exhausted.
        """
        if use_range:
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
            url: Optional[str] = f"{base}/calendarView"
            pages = 0
            # Follow @odata.nextLink until we have enough matches or run out.
            while url and len(events) < limit and pages < _MAX_PAGES:
                resp = requests.get(url, headers=headers, params=params, timeout=30)
                err = self._http_error(resp)
                if err:
                    raise _SearchError(err)
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
            return events[:limit]

        headers["ConsistencyLevel"] = "eventual"  # required for $search
        params = {"$search": f'"{query}"', "$top": limit, "$select": SELECT}
        resp = requests.get(f"{base}/events", headers=headers, params=params, timeout=30)
        err = self._http_error(resp)
        if err:
            raise _SearchError(err)
        return resp.json().get("value", [])[:limit]

    @staticmethod
    def _http_error(resp) -> Optional[str]:
        if resp.status_code == 401:
            return "Authentication failed. Token may be expired."
        if resp.status_code < 200 or resp.status_code >= 300:
            return describe_error(resp)
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

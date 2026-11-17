"""
The operations behind the ``google_calendar_*`` tools. Each takes the Google context and the tool
parameters and returns (output variables, JSON message, text message); ``run`` handles
credentials and errors, so every tool file is a thin wrapper (Dify loads one Tool class per file).
"""

import re
from datetime import date, timedelta
from typing import Any, Callable, Mapping

from tools.google_client import GoogleAuthError, GoogleContext, google_request, json_of, require, resolve_context, segment

API = "https://www.googleapis.com/calendar/v3"
SEND_UPDATES = ("all", "externalOnly", "none")
_OFFSET = re.compile(r"(Z|[+-]\d{2}:?\d{2})$")

Result = tuple[dict[str, Any], Any, str]


def run(tool: Any, params: Mapping[str, Any], op: Callable[[GoogleContext, Mapping[str, Any]], Result]):
    try:
        ctx = resolve_context(tool.runtime.credentials, tool)
        out, data, text = op(ctx, params)
    except GoogleAuthError as e:
        yield tool.create_text_message(str(e))
        return
    tool._out.update(out, success=True)
    yield tool.create_json_message(data)
    yield tool.create_text_message(text)


def calendar_url(p: Mapping[str, Any], *rest: str) -> str:
    calendar = str(p.get("calendar_id") or "primary").strip()
    return "/".join([f"{API}/calendars/{segment(calendar)}", *rest])


def send_updates(p: Mapping[str, Any]) -> str:
    value = str(p.get("send_updates") or "all").strip()
    if value not in SEND_UPDATES:
        raise GoogleAuthError(f"send_updates must be one of: {', '.join(SEND_UPDATES)}.")
    return value


def when(value: str, time_zone: str | None, all_day: bool) -> dict[str, str]:
    """A start/end object: {"date"} for all-day events, else {"dateTime"[, "timeZone"]}."""
    value = value.strip()
    if all_day:
        return {"date": value[:10]}
    if len(value) == 10:
        # A bare date for a timed event: midnight.
        value += "T00:00:00"
    result = {"dateTime": value}
    if time_zone:
        result["timeZone"] = time_zone
    elif not _OFFSET.search(value):
        raise GoogleAuthError(
            f"'{value}' has no UTC offset: give one (e.g. 2026-11-03T10:00:00+09:00) or set time_zone (e.g. Asia/Tokyo)."
        )
    return result


def event_dict(event: Mapping[str, Any]) -> dict[str, Any]:
    start = event.get("start") or {}
    end = event.get("end") or {}
    conference = (event.get("conferenceData") or {}).get("entryPoints") or []
    return {
        "id": event.get("id", ""),
        "title": event.get("summary", ""),
        "start": start.get("dateTime") or start.get("date", ""),
        "end": end.get("dateTime") or end.get("date", ""),
        "all_day": "date" in start,
        "time_zone": start.get("timeZone", ""),
        "location": event.get("location", ""),
        "description": event.get("description", ""),
        "status": event.get("status", ""),
        "organizer": (event.get("organizer") or {}).get("email", ""),
        "attendees": [
            {"email": a.get("email", ""), "response": a.get("responseStatus", "")} for a in event.get("attendees") or []
        ],
        "meeting_link": event.get("hangoutLink") or next((e.get("uri", "") for e in conference if e.get("entryPointType") == "video"), ""),
        "url": event.get("htmlLink", ""),
    }


def _summary(e: Mapping[str, Any]) -> str:
    parts = [f"{e['title'] or '(no title)'}: {e['start']} – {e['end']}"]
    if e["location"]:
        parts.append(f"at {e['location']}")
    if e["meeting_link"]:
        parts.append(f"join: {e['meeting_link']}")
    return ", ".join(parts)


# ── events ───────────────────────────────────────────────────────────


def get_event(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    (event_id,) = require(p, "event_id")
    event = event_dict(json_of(google_request(ctx, "GET", calendar_url(p, "events", segment(event_id)))))
    return {"event": event, "title": event["title"], "start": event["start"], "end": event["end"], "url": event["url"]}, event, _summary(event)


def update_event(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    (event_id,) = require(p, "event_id")
    url = calendar_url(p, "events", segment(event_id))
    current = json_of(google_request(ctx, "GET", url))
    patch: dict[str, Any] = {}
    for param, field in (("title", "summary"), ("description", "description"), ("location", "location"),
                         ("visibility", "visibility")):
        if p.get(param):
            patch[field] = str(p[param])
    all_day = p.get("all_day")
    all_day = ("date" in (current.get("start") or {})) if all_day is None else bool(all_day)
    time_zone = str(p.get("time_zone") or "").strip() or (current.get("start") or {}).get("timeZone")
    if p.get("start_time"):
        patch["start"] = when(str(p["start_time"]), time_zone, all_day)
    if p.get("end_time"):
        patch["end"] = when(str(p["end_time"]), time_zone, all_day)
    elif "start" in patch and all_day:
        # All-day end dates are exclusive: a one-day event ends the next day.
        patch["end"] = {"date": (date.fromisoformat(patch["start"]["date"]) + timedelta(days=1)).isoformat()}
    if p.get("attendees") is not None and str(p.get("attendees")).strip():
        emails = [e.strip() for e in str(p["attendees"]).split(",") if e.strip()]
        existing = {a.get("email") for a in current.get("attendees") or []}
        if str(p.get("attendees_mode") or "add") == "replace":
            patch["attendees"] = [{"email": e} for e in emails]
        else:
            patch["attendees"] = (current.get("attendees") or []) + [{"email": e} for e in emails if e not in existing]
    if not patch:
        raise GoogleAuthError("Nothing to update: give at least one field to change.")
    event = event_dict(json_of(google_request(ctx, "PATCH", url, params={"sendUpdates": send_updates(p)}, json_body=patch)))
    return ({"event_id": event["id"], "updated_fields": sorted(patch), "url": event["url"]}, event,
            f"Updated: {_summary(event)}")


def delete_event(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    (event_id,) = require(p, "event_id")
    google_request(ctx, "DELETE", calendar_url(p, "events", segment(event_id)), params={"sendUpdates": send_updates(p)})
    return {"deleted": True}, {"event_id": event_id, "deleted": True}, f"Deleted event {event_id}."


def check_availability(ctx: GoogleContext, p: Mapping[str, Any]) -> Result:
    time_min, time_max = require(p, "time_min", "time_max")
    calendars = [c.strip() for c in str(p.get("calendar_ids") or "primary").split(",") if c.strip()]
    body: dict[str, Any] = {"timeMin": time_min, "timeMax": time_max, "items": [{"id": c} for c in calendars]}
    if p.get("time_zone"):
        body["timeZone"] = p["time_zone"]
    result = json_of(google_request(ctx, "POST", f"{API}/freeBusy", json_body=body))
    busy: list[dict[str, Any]] = []
    errors = []
    for calendar_id, info in (result.get("calendars") or {}).items():
        errors += [f"{calendar_id}: {e.get('reason', 'error')}" for e in info.get("errors") or []]
        busy += [{"calendar": calendar_id, "start": b.get("start", ""), "end": b.get("end", "")} for b in info.get("busy") or []]
    busy.sort(key=lambda b: b["start"])
    free = not busy and not errors
    text = ("Free for the whole period." if free else
            "Busy: " + "; ".join(f"{b['start']} – {b['end']} ({b['calendar']})" for b in busy) if busy else "")
    if errors:
        text = (text + " " if text else "") + "Could not read: " + "; ".join(errors)
    return {"free": free, "busy": busy}, {"time_min": time_min, "time_max": time_max, "busy": busy, "errors": errors}, text

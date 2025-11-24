from __future__ import annotations

import urllib.parse
from collections.abc import Mapping, Sequence
from typing import Any

import requests

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError

_CAL_BASE = "https://www.googleapis.com/calendar/v3"


def collect_events(payload: Mapping[str, Any], key: str) -> list[dict[str, Any]]:
    raw_items = payload.get(key)
    if not isinstance(raw_items, Sequence):
        return []
    events: list[dict[str, Any]] = []
    for item in raw_items:
        if isinstance(item, Mapping):
            events.append(dict(item))
    return events


def resolve_calendar_id(runtime: Any, payload: Mapping[str, Any], parameters: Mapping[str, Any]) -> str:
    subscription_params: Mapping[str, Any] = {}
    if getattr(runtime, "subscription", None):
        subscription_params = runtime.subscription.parameters or {}
    calendar_id = (
        payload.get("calendarId")
        or parameters.get("calendar_id")
        or subscription_params.get("calendar_id")
        or "primary"
    )
    return str(calendar_id)


def get_access_token(runtime: Any) -> str:
    credentials: Mapping[str, Any] = {}
    if getattr(runtime, "credentials", None):
        credentials = runtime.credentials or {}
    token = credentials.get("access_token")
    if not token:
        raise ValueError("Missing Google Calendar OAuth access token in runtime credentials")
    return str(token)


def enrich_events(
    runtime: Any,
    *,
    calendar_id: str,
    events: list[dict[str, Any]],
    include_deleted: bool,
) -> list[dict[str, Any]]:
    if not events:
        return events

    access_token = get_access_token(runtime)
    headers = {"Authorization": f"Bearer {access_token}"}
    encoded_calendar = urllib.parse.quote(calendar_id, safe="@._-")

    enriched: list[dict[str, Any]] = []
    for event in events:
        event_id = str(event.get("id") or "").strip()
        if not event_id:
            continue
        encoded_event = urllib.parse.quote(event_id, safe="@._-")
        params = {"showDeleted": "true"} if include_deleted else None
        try:
            resp = requests.get(
                f"{_CAL_BASE}/calendars/{encoded_calendar}/events/{encoded_event}",
                headers=headers,
                params=params,
                timeout=10,
            )
        except requests.RequestException:
            enriched.append(event)
            continue

        if resp.status_code == 200:
            try:
                enriched.append(resp.json() or {})
            except Exception:
                enriched.append(event)
        elif resp.status_code == 404 and include_deleted:
            enriched.append(event)
        else:
            enriched.append(event)

    return enriched or events


def build_variables(payload: Mapping[str, Any], calendar_id: str, events: list[dict[str, Any]]) -> Variables:
    if not events:
        raise EventIgnoreError()

    variables = {
        "calendar_id": calendar_id,
        "resource_state": payload.get("resourceState"),
        "resource_id": payload.get("resourceId"),
        "channel_id": payload.get("channelId"),
        "next_sync_token": payload.get("nextSyncToken"),
        "events": events,
    }
    include_cancelled = payload.get("includeCancelled")
    if include_cancelled:
        variables["include_cancelled"] = include_cancelled

    return Variables(variables=variables)


def ensure_events_or_raise(events: list[dict[str, Any]]) -> None:
    if not events:
        raise EventIgnoreError()


def should_enrich_details(runtime: Any, parameters: Mapping[str, Any]) -> bool:
    if "enrich_event_details" in parameters:
        return bool(parameters.get("enrich_event_details"))

    if getattr(runtime, "subscription", None):
        subscription_params = runtime.subscription.parameters or {}
        if "enrich_event_details" in subscription_params:
            return bool(subscription_params.get("enrich_event_details"))

    return True


from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event

from .utils import (
    build_variables,
    collect_events,
    enrich_events,
    ensure_events_or_raise,
    resolve_calendar_id,
    should_enrich_details,
)


class GoogleCalendarEventCreatedEvent(Event):
    """Emit newly created Google Calendar events."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        _ = request  # placeholder for potential request validation

        events = collect_events(payload, "created")
        ensure_events_or_raise(events)

        calendar_id = resolve_calendar_id(self.runtime, payload, parameters)
        if should_enrich_details(self.runtime, parameters):
            enriched = enrich_events(self.runtime, calendar_id=calendar_id, events=events, include_deleted=False)
        else:
            enriched = events

        return build_variables(payload=payload, calendar_id=calendar_id, events=enriched)

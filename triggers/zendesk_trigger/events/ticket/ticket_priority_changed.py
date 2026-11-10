from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event

from ..utils import build_ticket_url, check_value_in, get_event, get_ticket, load_payload, resolve_subdomain


class TicketPriorityChangedEvent(Event):
    """Triggered when a Zendesk ticket's priority changes."""

    def _on_event(
        self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any] | None = None
    ) -> Variables:
        payload = load_payload(request, payload)
        ticket_data = get_ticket(payload)
        event = get_event(payload)

        # Zendesk sends upper-case values (e.g. "OPEN") and `null` when the priority was previously unset.
        current_priority = event.get("current")
        previous_priority = event.get("previous")

        check_value_in(previous_priority, parameters.get("from_priority"))
        check_value_in(current_priority, parameters.get("to_priority"))

        return Variables(
            variables={
                "ticket": ticket_data,
                "ticket_url": build_ticket_url(resolve_subdomain(self.runtime), ticket_data.get("id")),
                "current_priority": current_priority,
                "previous_priority": previous_priority,
            }
        )

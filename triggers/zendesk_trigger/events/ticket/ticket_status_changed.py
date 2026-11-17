from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event

from ..utils import build_ticket_url, check_value_in, get_event, get_ticket, load_payload, resolve_subdomain


class TicketStatusChangedEvent(Event):
    """Triggered when a Zendesk ticket's status changes."""

    def _on_event(
        self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any] | None = None
    ) -> Variables:
        payload = load_payload(request, payload)
        ticket_data = get_ticket(payload)
        event = get_event(payload)

        # Zendesk sends upper-case values (e.g. "OPEN") and `null` when the status was previously unset.
        current_status = event.get("current")
        previous_status = event.get("previous")

        check_value_in(previous_status, parameters.get("from_status"))
        check_value_in(current_status, parameters.get("to_status"))

        return Variables(
            variables={
                "ticket": ticket_data,
                "ticket_url": build_ticket_url(resolve_subdomain(self.runtime), ticket_data.get("id")),
                "current_status": current_status,
                "previous_status": previous_status,
            }
        )

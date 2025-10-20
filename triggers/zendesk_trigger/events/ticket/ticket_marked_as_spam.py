from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event

from ..utils import check_priority, check_status, check_tags


class TicketMarkedAsSpamEvent(Event):
    """Triggered when a Zendesk ticket is marked as spam."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        ticket_data = payload.get("detail", {})

        if not isinstance(ticket_data, Mapping):
            raise ValueError("Invalid ticket data in payload")

        # Apply filters to the spammed ticket data
        check_status(ticket_data, parameters.get("status"))
        check_priority(ticket_data, parameters.get("priority"))
        check_tags(ticket_data, parameters.get("tags"))

        return Variables(variables={"ticket": ticket_data})

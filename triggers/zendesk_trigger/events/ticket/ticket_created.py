from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event

from ..utils import (
    check_description_contains,
    check_priority,
    check_status,
    check_subject_contains,
    check_tags,
    check_type,
)


class TicketCreatedEvent(Event):
    """Triggered when a new Zendesk ticket is created."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        ticket_data = payload.get("detail", {})

        # Apply filters
        check_status(ticket_data, parameters.get("status"))
        check_priority(ticket_data, parameters.get("priority"))
        check_tags(ticket_data, parameters.get("tags"))
        check_type(ticket_data, parameters.get("type"))
        check_subject_contains(ticket_data, parameters.get("subject_contains"))
        check_description_contains(ticket_data, parameters.get("description_contains"))

        return Variables(variables={"ticket": ticket_data})

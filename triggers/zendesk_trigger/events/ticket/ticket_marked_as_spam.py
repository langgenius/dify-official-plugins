from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event

from ..utils import (
    build_ticket_url,
    check_priority,
    check_status,
    check_tags,
    get_ticket,
    load_payload,
    resolve_subdomain,
)


class TicketMarkedAsSpamEvent(Event):
    """Triggered when a Zendesk ticket is marked as spam."""

    def _on_event(
        self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any] | None = None
    ) -> Variables:
        payload = load_payload(request, payload)
        ticket_data = get_ticket(payload)

        check_status(ticket_data, parameters.get("status"))
        check_priority(ticket_data, parameters.get("priority"))
        check_tags(ticket_data, parameters.get("tags"))

        return Variables(
            variables={
                "ticket": ticket_data,
                "ticket_url": build_ticket_url(resolve_subdomain(self.runtime), ticket_data.get("id")),
            }
        )

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class TicketPriorityChangedEvent(Event):
    """Triggered when a Zendesk ticket's priority changes."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        ticket_data = payload.get("detail", {})

        current_priority = payload.get("event", {}).get("current", "").lower()
        previous_priority = payload.get("event", {}).get("previous", "").lower()

        # Filter by from_priority
        from_priority_param = parameters.get("from_priority")
        if from_priority_param:
            allowed_from = [p.strip().lower() for p in from_priority_param.split(",")]
            if previous_priority not in allowed_from:
                raise EventIgnoreError()

        # Filter by to_priority
        to_priority_param = parameters.get("to_priority")
        if to_priority_param:
            allowed_to = [p.strip().lower() for p in to_priority_param.split(",")]
            if current_priority not in allowed_to:
                raise EventIgnoreError()

        return Variables(variables={"ticket": ticket_data})

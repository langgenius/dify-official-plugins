from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class TicketStatusChangedEvent(Event):
    """Triggered when a Zendesk ticket's status changes."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        ticket_data = payload.get("detail", {})

        current_status = payload.get("event", {}).get("current", "").lower()
        previous_status = payload.get("event", {}).get("previous", "").lower()

        # Filter by from_status
        from_status_param = parameters.get("from_status")
        if from_status_param:
            allowed_from = [s.strip().lower() for s in from_status_param.split(",")]
            if previous_status not in allowed_from:
                raise EventIgnoreError()

        # Filter by to_status
        to_status_param = parameters.get("to_status")
        if to_status_param:
            allowed_to = [s.strip().lower() for s in to_status_param.split(",")]
            if current_status not in allowed_to:
                raise EventIgnoreError()

        return Variables(variables={"ticket": ticket_data})

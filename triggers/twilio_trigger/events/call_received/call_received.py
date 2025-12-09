from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event

from events.utils.filters import check_from_filter, check_call_status


class CallReceivedEvent(Event):
    """Call received event handler."""

    def _on_event(
        self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]
    ) -> Variables:
        # Payload is already parsed from form data by the trigger
        if not payload:
            raise ValueError("No payload received")

        # Apply filters
        from_number = payload.get("From", "")
        call_status = payload.get("CallStatus", "")

        check_from_filter(from_number, parameters.get("from_filter"))
        check_call_status(call_status, parameters.get("call_status_filter"))

        return Variables(variables=dict(payload))

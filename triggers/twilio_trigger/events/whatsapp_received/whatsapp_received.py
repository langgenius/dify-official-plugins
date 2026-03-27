from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event

from events.utils.filters import apply_message_filters, check_profile_name


class WhatsappReceivedEvent(Event):
    """WhatsApp message received event handler."""

    def _on_event(
        self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]
    ) -> Variables:
        # Payload is already parsed from form data by the trigger
        if not payload:
            raise ValueError("No payload received")

        # Apply common message filters
        apply_message_filters(payload, parameters)

        # Apply WhatsApp-specific filters
        profile_name = payload.get("ProfileName")
        check_profile_name(profile_name, parameters.get("profile_name_filter"))

        return Variables(variables=dict(payload))

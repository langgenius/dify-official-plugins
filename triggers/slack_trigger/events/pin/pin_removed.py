from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent
from ..utils.filters import check_channel_id, check_user_id


class PinRemovedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `pin.removed`."""

    EVENT_KEY = "pin_removed"

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        raw_payload = request.get_json(silent=True) or {}
        event = raw_payload.get("event") or {}
        # pin events use "channel_id" field (not "channel")
        check_channel_id(event, parameters.get("channel_id"), field="channel_id")
        check_user_id(event, parameters.get("user_id"))
        return super()._on_event(request, parameters, payload)

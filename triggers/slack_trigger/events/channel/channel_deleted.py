from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent
from ..utils.filters import check_channel_id


class ChannelDeletedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `channel.deleted`."""

    EVENT_KEY = "channel_deleted"

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        raw_payload = request.get_json(silent=True) or {}
        event = raw_payload.get("event") or {}
        # channel_deleted: event["channel"] is a plain string ID
        check_channel_id(event, parameters.get("channel_id"))
        return super()._on_event(request, parameters, payload)

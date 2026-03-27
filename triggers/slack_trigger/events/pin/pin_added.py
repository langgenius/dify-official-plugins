from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent
from ..utils.filters import check_channel_id, check_user_id


class PinAddedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `pin.added`."""

    EVENT_KEY = "pin_added"

    def _apply_filters(self, event: Mapping[str, Any], parameters: Mapping[str, Any]) -> None:
        # pin events use "channel_id" field (not "channel")
        check_channel_id(event, parameters.get("channel_id"), field="channel_id")
        check_user_id(event, parameters.get("user_id"))

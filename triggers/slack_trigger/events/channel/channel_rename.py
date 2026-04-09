from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent
from ..utils.filters import check_channel_id


class ChannelRenameEvent(CatalogSlackEvent, Event):
    """Slack event handler for `channel.rename`."""

    EVENT_KEY = "channel_rename"

    def _apply_filters(self, event: Mapping[str, Any], parameters: Mapping[str, Any]) -> None:
        # channel_rename: event["channel"] is an object with an "id" key
        check_channel_id(event, parameters.get("channel_id"))

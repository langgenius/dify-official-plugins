from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent
from ..utils.filters import check_channel_id


class ChannelArchiveEvent(CatalogSlackEvent, Event):
    """Slack event handler for `channel.archive`."""

    EVENT_KEY = "channel_archive"

    def _apply_filters(self, event: Mapping[str, Any], parameters: Mapping[str, Any]) -> None:
        # channel_archive: event["channel"] is a plain string ID
        check_channel_id(event, parameters.get("channel_id"))

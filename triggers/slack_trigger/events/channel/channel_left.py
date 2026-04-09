from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class ChannelLeftEvent(CatalogSlackEvent, Event):
    """Slack event handler for `channel.left`."""

    EVENT_KEY = "channel_left"

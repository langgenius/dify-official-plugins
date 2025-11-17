from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class ChannelUnarchiveEvent(CatalogSlackEvent, Event):
    """Slack event handler for `channel.unarchive`."""

    EVENT_KEY = "channel_unarchive"

from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class ChannelDeletedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `channel.deleted`."""

    EVENT_KEY = "channel_deleted"

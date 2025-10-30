from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class ChannelCreatedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `channel.created`."""

    EVENT_KEY = "channel_created"

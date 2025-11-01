from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class MessageChannelsEvent(CatalogSlackEvent, Event):
    """Slack event handler for `message.channels`."""

    EVENT_KEY = "message_channels"

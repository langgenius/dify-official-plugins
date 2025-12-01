from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class MessageMpimEvent(CatalogSlackEvent, Event):
    """Slack event handler for `message.mpim`."""

    EVENT_KEY = "message_mpim"

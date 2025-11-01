from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class MessageEvent(CatalogSlackEvent, Event):
    """Slack event handler for `message`."""

    EVENT_KEY = "message"

from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class PinAddedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `pin.added`."""

    EVENT_KEY = "pin_added"

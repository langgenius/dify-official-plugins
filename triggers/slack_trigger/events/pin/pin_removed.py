from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class PinRemovedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `pin.removed`."""

    EVENT_KEY = "pin_removed"

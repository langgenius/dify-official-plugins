from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class StarRemovedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `star.removed`."""

    EVENT_KEY = "star_removed"

from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class StarAddedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `star.added`."""

    EVENT_KEY = "star_added"

from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class ResourcesAddedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `resources.added`."""

    EVENT_KEY = "resources_added"

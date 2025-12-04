from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class ResourcesRemovedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `resources.removed`."""

    EVENT_KEY = "resources_removed"

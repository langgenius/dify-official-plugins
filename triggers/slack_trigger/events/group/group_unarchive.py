from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class GroupUnarchiveEvent(CatalogSlackEvent, Event):
    """Slack event handler for `group.unarchive`."""

    EVENT_KEY = "group_unarchive"

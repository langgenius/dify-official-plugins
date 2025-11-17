from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class GroupLeftEvent(CatalogSlackEvent, Event):
    """Slack event handler for `group.left`."""

    EVENT_KEY = "group_left"

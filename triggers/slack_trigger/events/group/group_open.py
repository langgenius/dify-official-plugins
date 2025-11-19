from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class GroupOpenEvent(CatalogSlackEvent, Event):
    """Slack event handler for `group.open`."""

    EVENT_KEY = "group_open"

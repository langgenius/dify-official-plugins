from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class GroupCloseEvent(CatalogSlackEvent, Event):
    """Slack event handler for `group.close`."""

    EVENT_KEY = "group_close"

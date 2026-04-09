from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class GroupHistoryChangedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `group.history.changed`."""

    EVENT_KEY = "group_history_changed"

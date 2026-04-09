from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class ChannelHistoryChangedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `channel.history.changed`."""

    EVENT_KEY = "channel_history_changed"

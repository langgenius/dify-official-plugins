from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class ImHistoryChangedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `im.history.changed`."""

    EVENT_KEY = "im_history_changed"

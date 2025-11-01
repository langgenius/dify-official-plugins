from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class FileChangeEvent(CatalogSlackEvent, Event):
    """Slack event handler for `file.change`."""

    EVENT_KEY = "file_change"

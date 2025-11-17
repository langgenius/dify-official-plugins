from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class FileDeletedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `file.deleted`."""

    EVENT_KEY = "file_deleted"

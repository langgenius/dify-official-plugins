from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class FileSharedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `file.shared`."""

    EVENT_KEY = "file_shared"

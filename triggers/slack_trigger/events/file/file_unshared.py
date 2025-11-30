from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class FileUnsharedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `file.unshared`."""

    EVENT_KEY = "file_unshared"

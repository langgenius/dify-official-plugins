from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class FilePublicEvent(CatalogSlackEvent, Event):
    """Slack event handler for `file.public`."""

    EVENT_KEY = "file_public"

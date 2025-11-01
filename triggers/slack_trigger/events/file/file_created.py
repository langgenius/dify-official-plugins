from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class FileCreatedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `file.created`."""

    EVENT_KEY = "file_created"

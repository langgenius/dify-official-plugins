from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class GroupArchiveEvent(CatalogSlackEvent, Event):
    """Slack event handler for `group.archive`."""

    EVENT_KEY = "group_archive"

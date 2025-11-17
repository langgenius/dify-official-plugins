from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class GroupRenameEvent(CatalogSlackEvent, Event):
    """Slack event handler for `group.rename`."""

    EVENT_KEY = "group_rename"

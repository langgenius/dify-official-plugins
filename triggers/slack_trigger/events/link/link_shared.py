from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class LinkSharedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `link.shared`."""

    EVENT_KEY = "link_shared"

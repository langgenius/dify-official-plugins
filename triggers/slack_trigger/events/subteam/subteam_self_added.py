from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class SubteamSelfAddedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `subteam.self.added`."""

    EVENT_KEY = "subteam_self_added"

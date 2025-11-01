from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class SubteamUpdatedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `subteam.updated`."""

    EVENT_KEY = "subteam_updated"

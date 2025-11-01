from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class SubteamCreatedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `subteam.created`."""

    EVENT_KEY = "subteam_created"

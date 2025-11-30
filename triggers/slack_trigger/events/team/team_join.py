from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class TeamJoinEvent(CatalogSlackEvent, Event):
    """Slack event handler for `team.join`."""

    EVENT_KEY = "team_join"

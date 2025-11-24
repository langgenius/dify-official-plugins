from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class TeamRenameEvent(CatalogSlackEvent, Event):
    """Slack event handler for `team.rename`."""

    EVENT_KEY = "team_rename"

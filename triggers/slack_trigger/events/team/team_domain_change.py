from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class TeamDomainChangeEvent(CatalogSlackEvent, Event):
    """Slack event handler for `team.domain.change`."""

    EVENT_KEY = "team_domain_change"

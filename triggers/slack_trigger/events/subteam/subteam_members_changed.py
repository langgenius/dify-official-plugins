from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class SubteamMembersChangedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `subteam.members.changed`."""

    EVENT_KEY = "subteam_members_changed"

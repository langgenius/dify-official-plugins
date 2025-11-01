from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class MemberJoinedChannelEvent(CatalogSlackEvent, Event):
    """Slack event handler for `member.joined.channel`."""

    EVENT_KEY = "member_joined_channel"

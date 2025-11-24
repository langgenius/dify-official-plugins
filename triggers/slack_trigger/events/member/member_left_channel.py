from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class MemberLeftChannelEvent(CatalogSlackEvent, Event):
    """Slack event handler for `member.left.channel`."""

    EVENT_KEY = "member_left_channel"

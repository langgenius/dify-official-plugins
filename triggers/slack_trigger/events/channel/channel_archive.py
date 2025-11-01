from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class ChannelArchiveEvent(CatalogSlackEvent, Event):
    """Slack event handler for `channel.archive`."""

    EVENT_KEY = "channel_archive"

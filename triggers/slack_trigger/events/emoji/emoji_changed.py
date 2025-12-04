from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class EmojiChangedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `emoji.changed`."""

    EVENT_KEY = "emoji_changed"

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent
from ..utils.filters import check_emoji_subtype


class EmojiChangedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `emoji.changed`."""

    EVENT_KEY = "emoji_changed"

    def _apply_filters(self, event: Mapping[str, Any], parameters: Mapping[str, Any]) -> None:
        check_emoji_subtype(event, parameters.get("subtype"))

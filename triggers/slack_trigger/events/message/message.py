from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent
from ..utils.filters import check_bot_filter, check_channel_id, check_text_contains, check_user_id


class MessageEvent(CatalogSlackEvent, Event):
    """Slack event handler for `message`."""

    EVENT_KEY = "message"

    def _apply_filters(self, event: Mapping[str, Any], parameters: Mapping[str, Any]) -> None:
        check_channel_id(event, parameters.get("channel_id"))
        check_user_id(event, parameters.get("user_id"))
        check_text_contains(event, parameters.get("text_contains"))
        check_bot_filter(event, parameters.get("bot_filter"))

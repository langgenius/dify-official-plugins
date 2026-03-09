from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent
from ..utils.filters import check_emoji_subtype


class EmojiChangedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `emoji.changed`."""

    EVENT_KEY = "emoji_changed"

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        raw_payload = request.get_json(silent=True) or {}
        event = raw_payload.get("event") or {}
        check_emoji_subtype(event, parameters.get("subtype"))
        return super()._on_event(request, parameters, payload)

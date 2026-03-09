from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent
from ..utils.filters import check_bot_filter, check_text_contains, check_user_id


class MessageAppHomeEvent(CatalogSlackEvent, Event):
    """Slack event handler for `message.app.home`."""

    EVENT_KEY = "message_app_home"

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        raw_payload = request.get_json(silent=True) or {}
        event = raw_payload.get("event") or {}
        # App Home messages are always DM-like; channel_id filter is not applicable
        check_user_id(event, parameters.get("user_id"))
        check_text_contains(event, parameters.get("text_contains"))
        check_bot_filter(event, parameters.get("bot_filter"))
        return super()._on_event(request, parameters, payload)

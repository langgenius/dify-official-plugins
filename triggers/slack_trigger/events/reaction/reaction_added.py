from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent
from ..utils.filters import check_reaction, check_reaction_item_type, check_user_id


class ReactionAddedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `reaction.added`."""

    EVENT_KEY = "reaction_added"

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        raw_payload = request.get_json(silent=True) or {}
        event = raw_payload.get("event") or {}
        check_reaction(event, parameters.get("reaction"))
        check_reaction_item_type(event, parameters.get("item_type"))
        check_user_id(event, parameters.get("user_id"))
        return super()._on_event(request, parameters, payload)

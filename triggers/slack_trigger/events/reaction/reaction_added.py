from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent
from ..utils.filters import check_item_channel_id, check_reaction, check_reaction_item_type, check_user_id


class ReactionAddedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `reaction.added`."""

    EVENT_KEY = "reaction_added"

    def _apply_filters(self, event: Mapping[str, Any], parameters: Mapping[str, Any]) -> None:
        check_item_channel_id(event, parameters.get("channel_id"))
        check_reaction(event, parameters.get("reaction"))
        check_reaction_item_type(event, parameters.get("item_type"))
        check_user_id(event, parameters.get("user_id"))

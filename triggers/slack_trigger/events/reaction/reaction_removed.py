from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent
from ..utils.filters import check_reaction, check_reaction_item_type, check_user_id


class ReactionRemovedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `reaction.removed`."""

    EVENT_KEY = "reaction_removed"

    def _apply_filters(self, event: Mapping[str, Any], parameters: Mapping[str, Any]) -> None:
        check_reaction(event, parameters.get("reaction"))
        check_reaction_item_type(event, parameters.get("item_type"))
        check_user_id(event, parameters.get("user_id"))

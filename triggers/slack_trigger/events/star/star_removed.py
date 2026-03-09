from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent
from ..utils.filters import check_star_item_type


class StarRemovedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `star.removed`."""

    EVENT_KEY = "star_removed"

    def _apply_filters(self, event: Mapping[str, Any], parameters: Mapping[str, Any]) -> None:
        check_star_item_type(event, parameters.get("item_type"))

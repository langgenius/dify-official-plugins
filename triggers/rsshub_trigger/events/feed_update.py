from __future__ import annotations

from typing import Any, Mapping

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event


class FeedUpdateEvent(Event):
    """rss.app-compatible feed_update event."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        # Pass through as-is to match documented schema
        return Variables(variables={**request.get_json()})

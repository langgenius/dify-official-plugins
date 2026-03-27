from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class GollumEvent(Event):
    """Gollum (Wiki) event for page created/edited."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        pages = payload.get("pages")
        if not isinstance(pages, list):
            raise ValueError("No pages in payload")

        actions_filter = set(parameters.get("actions") or [])
        title_filter = parameters.get("title")

        def match_page(page: Mapping[str, Any]) -> bool:
            if actions_filter and (page.get("action") or "") not in actions_filter:
                return False
            if title_filter:
                titles = {v.strip() for v in str(title_filter).split(",") if v.strip()}
                if titles and (page.get("title") or "") not in titles:
                    return False
            return True

        any_match = any(isinstance(p, Mapping) and match_page(p) for p in pages)
        if (actions_filter or title_filter) and not any_match:
            raise EventIgnoreError()

        return Variables(variables={**payload})

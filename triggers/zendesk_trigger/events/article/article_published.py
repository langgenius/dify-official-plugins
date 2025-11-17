from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class ArticlePublishedEvent(Event):
    """Triggered when a Zendesk knowledge base article is published."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        detail = payload.get("detail", {})
        event_meta = payload.get("event", {})

        if not isinstance(detail, Mapping) or not isinstance(event_meta, Mapping):
            raise ValueError("Invalid article payload")

        # Normalize string helpers
        def _lower(value: Any) -> str:
            return str(value).lower() if isinstance(value, str) else ""

        # Filter by locale
        locale_param = parameters.get("locale")
        if locale_param:
            article_locale = _lower(event_meta.get("locale"))
            allowed_locales = [_lower(loc.strip()) for loc in locale_param.split(",")]
            if article_locale not in allowed_locales:
                raise EventIgnoreError()

        # Filter by title
        title_contains = parameters.get("title_contains")
        if title_contains:
            title = event_meta.get("title", "")
            if not isinstance(title, str) or not title:
                raise EventIgnoreError()

            keywords = [_lower(k.strip()) for k in title_contains.split(",")]
            title_lower = title.lower()

            if not any(keyword and keyword in title_lower for keyword in keywords):
                raise EventIgnoreError()

        article_payload = {
            "id": detail.get("id"),
            "brand_id": detail.get("brand_id"),
            "user_id": detail.get("user_id"),
            "author_id": event_meta.get("author_id"),
            "category_id": event_meta.get("category_id"),
            "section_id": event_meta.get("section_id"),
            "locale": event_meta.get("locale"),
            "title": event_meta.get("title"),
        }

        return Variables(variables={"article": article_payload})

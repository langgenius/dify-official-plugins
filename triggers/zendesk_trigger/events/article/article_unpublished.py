from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class ArticleUnpublishedEvent(Event):
    """Triggered when a Zendesk help center article is unpublished."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        detail = payload.get("detail", {})
        if not isinstance(detail, Mapping):
            raise ValueError("Invalid article data in payload")

        # Optional filters
        brand_filter = parameters.get("brand_ids")
        if brand_filter:
            allowed_brands = {bid.strip() for bid in brand_filter.split(",") if bid.strip()}
            if allowed_brands:
                brand_id = str(detail.get("brand_id", "")) if detail.get("brand_id") is not None else ""
                if brand_id not in allowed_brands:
                    raise EventIgnoreError()

        user_filter = parameters.get("user_ids")
        if user_filter:
            allowed_users = {uid.strip() for uid in user_filter.split(",") if uid.strip()}
            if allowed_users:
                user_id = str(detail.get("user_id", "")) if detail.get("user_id") is not None else ""
                if user_id not in allowed_users:
                    raise EventIgnoreError()

        article_payload = {
            "id": detail.get("id"),
            "brand_id": detail.get("brand_id"),
            "user_id": detail.get("user_id"),
            "unpublished_at": payload.get("time"),
        }

        return Variables(variables={"article": article_payload})

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class DiscussionCommentUnifiedEvent(Event):
    """Unified Discussion Comment event (created/edited/deleted)."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        allowed_actions = parameters.get("actions") or []
        action = payload.get("action")
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        comment = payload.get("comment")
        if not isinstance(comment, Mapping):
            raise ValueError("No comment in payload")

        self._check_body_contains(comment, parameters.get("body_contains"))
        self._check_commenter(comment, parameters.get("commenter"))

        return Variables(variables={**payload})

    def _check_body_contains(self, comment: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        keywords = {v.strip().lower() for v in str(value).split(",") if v.strip()}
        body = (comment.get("body") or "").lower()
        if keywords and not any(k in body for k in keywords):
            raise EventIgnoreError()

    def _check_commenter(self, comment: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        allowed = {v.strip() for v in str(value).split(",") if v.strip()}
        login = ((comment.get("user") or {}).get("login") or "").strip()
        if allowed and login not in allowed:
            raise EventIgnoreError()


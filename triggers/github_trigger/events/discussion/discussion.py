from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class DiscussionUnifiedEvent(Event):
    """Unified Discussion event (created/edited/deleted/answered/labeled/unlabeled/category_changed)."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        allowed_actions = parameters.get("actions") or []
        action = payload.get("action")
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        discussion = payload.get("discussion")
        if not isinstance(discussion, Mapping):
            raise ValueError("No discussion in payload")

        self._check_category(discussion, parameters.get("category"))
        self._check_author(discussion, parameters.get("author"))
        self._check_title_body(discussion, parameters.get("title_contains"), parameters.get("body_contains"))

        return Variables(variables={**payload})

    def _check_category(self, discussion: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        cats = {v.strip() for v in str(value).split(",") if v.strip()}
        name = ((discussion.get("category") or {}).get("name") or "").strip()
        if cats and name not in cats:
            raise EventIgnoreError()

    def _check_author(self, discussion: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        authors = {v.strip() for v in str(value).split(",") if v.strip()}
        login = ((discussion.get("user") or {}).get("login") or "").strip()
        if authors and login not in authors:
            raise EventIgnoreError()

    def _check_title_body(self, discussion: Mapping[str, Any], title_value: str | None, body_value: str | None) -> None:
        if title_value:
            kws = {v.strip().lower() for v in str(title_value).split(",") if v.strip()}
            title = (discussion.get("title") or "").lower()
            if kws and not any(k in title for k in kws):
                raise EventIgnoreError()
        if body_value:
            kws = {v.strip().lower() for v in str(body_value).split(",") if v.strip()}
            body = (discussion.get("body") or "").lower()
            if kws and not any(k in body for k in kws):
                raise EventIgnoreError()


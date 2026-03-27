from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class CommitCommentEvent(Event):
    """Unified commit comment event (typically 'created')."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        allowed_actions = parameters.get("actions") or []
        action = (payload.get("action") or "created").lower()
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        comment = payload.get("comment")
        if not isinstance(comment, Mapping):
            raise ValueError("No comment in payload")

        self._check_body_contains(comment, parameters.get("body_contains"))
        self._check_commenter(comment, parameters.get("commenter"))
        self._check_commit_id(payload, parameters.get("commit_id"))
        self._check_path(comment, parameters.get("path"))

        return Variables(variables={**payload})

    def _check_body_contains(self, comment: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        keywords = {s.strip().lower() for s in str(value).split(",") if s.strip()}
        body = (comment.get("body") or "").lower()
        if keywords and not any(k in body for k in keywords):
            raise EventIgnoreError()

    def _check_commenter(self, comment: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        allowed = {s.strip() for s in str(value).split(",") if s.strip()}
        login = (comment.get("user", {}) or {}).get("login")
        if allowed and login not in allowed:
            raise EventIgnoreError()

    def _check_commit_id(self, payload: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        cid = (payload.get("comment") or {}).get("commit_id") or payload.get("commit_id")
        targets = {s.strip() for s in str(value).split(",") if s.strip()}
        if targets and (cid not in targets):
            raise EventIgnoreError()

    def _check_path(self, comment: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        path = (comment.get("path") or "").strip()
        targets = {s.strip() for s in str(value).split(",") if s.strip()}
        if targets and path not in targets:
            raise EventIgnoreError()

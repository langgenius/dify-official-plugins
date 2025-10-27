from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class PullRequestReviewThreadUnifiedEvent(Event):
    """Unified PR review thread event (resolved/unresolved/edited/created)."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        allowed_actions = parameters.get("actions") or []
        action = payload.get("action")
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        thread = payload.get("thread")
        if not isinstance(thread, Mapping):
            raise ValueError("No thread in payload")

        if parameters.get("is_resolved") is not None:
            want = str(parameters.get("is_resolved")).lower() in {"true", "1", "yes"}
            if bool(thread.get("is_resolved")) != want:
                raise EventIgnoreError()

        author = parameters.get("author")
        if author:
            allowed = {v.strip() for v in str(author).split(",") if v.strip()}
            comments = thread.get("comments") or []
            found = False
            if isinstance(comments, list):
                for c in comments:
                    u = (c or {}).get("user") or {}
                    if (u.get("login") or "") in allowed:
                        found = True
                        break
            if allowed and not found:
                raise EventIgnoreError()

        path_filter = parameters.get("path")
        if path_filter:
            paths = {v.strip() for v in str(path_filter).split(",") if v.strip()}
            comments = thread.get("comments") or []

            def any_path_match() -> bool:
                if not isinstance(comments, list):
                    return False
                return any((c or {}).get("path") in paths for c in comments)

            if paths and not any_path_match():
                raise EventIgnoreError()

        return Variables(variables={**payload})

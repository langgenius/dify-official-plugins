from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class SubIssuesUnifiedEvent(Event):
    """Unified Sub Issues event (added/removed/updated relationships)."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        allowed_actions = parameters.get("actions") or []
        action = payload.get("action")
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        sub_issue = payload.get("sub_issue")
        if not isinstance(sub_issue, Mapping):
            sub_issue = {}

        parent_issue = payload.get("parent_issue")
        if not isinstance(parent_issue, Mapping):
            parent_issue = {}

        parent_filter = parameters.get("parent_issue")
        if parent_filter:
            numbers = {int(v.strip()) for v in str(parent_filter).split(",") if v.strip().isdigit()}
            if numbers and (parent_issue.get("number") or 0) not in numbers:
                raise EventIgnoreError()

        child_filter = parameters.get("child_issue")
        if child_filter:
            numbers = {int(v.strip()) for v in str(child_filter).split(",") if v.strip().isdigit()}
            if numbers and (sub_issue.get("number") or 0) not in numbers:
                raise EventIgnoreError()

        return Variables(variables={**payload})


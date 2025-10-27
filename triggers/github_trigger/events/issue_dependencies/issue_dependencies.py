from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class IssueDependenciesUnifiedEvent(Event):
    """Unified Issue Dependencies event (added/removed)."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        allowed_actions = parameters.get("actions") or []
        action = payload.get("action")
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        dependency = payload.get("dependency")
        if not isinstance(dependency, Mapping):
            # Some previews may use different keys; fall back to pass-through
            dependency = {}

        parent_issue_filter = parameters.get("parent_issue")
        if parent_issue_filter:
            numbers = {int(v.strip()) for v in str(parent_issue_filter).split(",") if v.strip().isdigit()}
            parent = ((dependency.get("dependent_issue") or {}) or {}).get("number")
            if numbers and parent not in numbers:
                raise EventIgnoreError()

        child_issue_filter = parameters.get("child_issue")
        if child_issue_filter:
            numbers = {int(v.strip()) for v in str(child_issue_filter).split(",") if v.strip().isdigit()}
            child = ((dependency.get("blocking_issue") or {}) or {}).get("number")
            if numbers and child not in numbers:
                raise EventIgnoreError()

        return Variables(variables={**payload})

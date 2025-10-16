from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class BranchProtectionRuleEvent(Event):
    """Unified branch protection rule event."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        allowed_actions = parameters.get("actions") or []
        action = payload.get("action")
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        pattern_filter = parameters.get("pattern")
        if pattern_filter:
            rule = payload.get("rule") or {}
            pat = (rule.get("pattern") or "").strip()
            targets = {s.strip() for s in str(pattern_filter).split(",") if s.strip()}
            if targets and pat not in targets:
                raise EventIgnoreError()

        return Variables(variables={**payload})


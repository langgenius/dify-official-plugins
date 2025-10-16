from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class RepositoryRulesetEvent(Event):
    """Unified repository ruleset event."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        allowed_actions = parameters.get("actions") or []
        action = payload.get("action")
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        name_filter = parameters.get("name")
        if name_filter:
            ruleset = payload.get("ruleset") or {}
            name = (ruleset.get("name") or "").strip()
            targets = {s.strip() for s in str(name_filter).split(",") if s.strip()}
            if targets and name not in targets:
                raise EventIgnoreError()

        return Variables(variables={**payload})


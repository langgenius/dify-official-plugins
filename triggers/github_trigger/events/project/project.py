from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class ProjectUnifiedEvent(Event):
    """Unified Project event (created/edited/deleted/closed/reopened)."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        allowed_actions = parameters.get("actions") or []
        action = payload.get("action")
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        project = payload.get("project")
        if not isinstance(project, Mapping):
            raise ValueError("No project in payload")

        name_filter = parameters.get("project_name")
        if name_filter:
            names = {v.strip() for v in str(name_filter).split(",") if v.strip()}
            if names and (project.get("name") or "") not in names:
                raise EventIgnoreError()

        state_filter = parameters.get("state")
        if state_filter:
            states = {v.strip().lower() for v in str(state_filter).split(",") if v.strip()}
            if states and (str(project.get("state") or "").lower()) not in states:
                raise EventIgnoreError()

        return Variables(variables={**payload})


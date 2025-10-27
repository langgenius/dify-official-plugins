from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event

from ..utils import issues as isu


class IssuesUnifiedEvent(Event):
    """Unified Issues event. Filters by actions and common issue attributes."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        allowed_actions = parameters.get("actions") or []
        action = payload.get("action")
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        issue = payload.get("issue")
        if not isinstance(issue, Mapping):
            raise ValueError("No issue in payload")

        isu.check_labels(issue, parameters.get("labels"))
        isu.check_assignee(issue, parameters.get("assignee"))
        isu.check_authors(issue, parameters.get("authors"))
        isu.check_milestone(issue, parameters.get("milestone"))
        isu.check_title_contains(issue, parameters.get("title_contains"))
        isu.check_body_contains(issue, parameters.get("body_contains"))
        isu.check_state(issue, parameters.get("state"))

        return Variables(variables={**payload})

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event

from ..utils.pull_request import (
    apply_pull_request_common_filters,
    check_merged_state,
)


class PullRequestUnifiedEvent(Event):
    """Unified Pull Request event with actions filter."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        allowed_actions = parameters.get("actions") or []
        action = payload.get("action")
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        pr = payload.get("pull_request")
        if not isinstance(pr, Mapping):
            raise ValueError("No pull_request in payload")

        apply_pull_request_common_filters(pr, parameters)
        if action == "closed":
            check_merged_state(pr, parameters.get("merged"))

        return Variables(variables={**payload})


from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event

from ..utils import issue_comment as icu


class IssueCommentUnifiedEvent(Event):
    """Unified Issue Comment event (created/edited/deleted)."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        allowed_actions = parameters.get("actions") or []
        action = payload.get("action")
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        comment = payload.get("comment")
        issue = payload.get("issue")
        if not isinstance(comment, Mapping) or not isinstance(issue, Mapping):
            raise ValueError("Missing comment or issue in payload")

        icu.check_comment_body_contains(comment, parameters.get("comment_body_contains"))
        icu.check_commenter(comment, parameters.get("commenter"))
        icu.check_issue_labels(issue, parameters.get("issue_labels"))
        icu.check_issue_state(issue, parameters.get("issue_state"))
        icu.check_is_pull_request(issue, parameters.get("is_pull_request"))

        return Variables(variables={**payload})


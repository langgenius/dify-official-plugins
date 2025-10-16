from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event

from ..utils.pull_request_review_comment import (
    apply_pull_request_review_comment_filters,
    check_comment_deleter,
    load_pull_request_review_comment_payload,
)


class PullRequestReviewCommentUnifiedEvent(Event):
    """Unified PR review comment event (created/edited/deleted)."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload, comment, pull_request = load_pull_request_review_comment_payload(request, expected_action=None)

        allowed_actions = parameters.get("actions") or []
        action = payload.get("action")
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        apply_pull_request_review_comment_filters(comment, pull_request, parameters)
        if action == "deleted":
            check_comment_deleter(payload, parameters.get("deleter"))

        return Variables(variables={**payload})


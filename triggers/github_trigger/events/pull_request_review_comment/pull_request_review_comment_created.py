from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event

from ..utils.pull_request_review_comment import (
    apply_pull_request_review_comment_filters,
    load_pull_request_review_comment_payload,
)


class PullRequestReviewCommentCreatedEvent(Event):
    """GitHub Pull Request Review Comment Created Event"""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload, comment, pull_request = load_pull_request_review_comment_payload(
            request,
            expected_action="created",
        )
        apply_pull_request_review_comment_filters(comment, pull_request, parameters)
        return Variables(variables={**payload})

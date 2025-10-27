from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event

from ..utils.pull_request_review_comment import (
    apply_pull_request_review_comment_filters,
    check_comment_deleter,
    load_pull_request_review_comment_payload,
)


class PullRequestReviewCommentDeletedEvent(Event):
    """GitHub Pull Request Review Comment Deleted Event"""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload, comment, pull_request = load_pull_request_review_comment_payload(
            request,
            expected_action="deleted",
        )
        apply_pull_request_review_comment_filters(comment, pull_request, parameters)
        check_comment_deleter(payload, parameters.get("deleter"))
        return Variables(variables={**payload})

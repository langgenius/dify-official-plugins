from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event

from ..utils.pull_request_review import (
    apply_pull_request_review_filters,
    load_pull_request_review_payload,
)


class PullRequestReviewSubmittedEvent(Event):
    """GitHub Pull Request Review Submitted Event"""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload, review, pull_request = load_pull_request_review_payload(request, expected_action="submitted")
        apply_pull_request_review_filters(review, pull_request, parameters)
        return Variables(variables={**payload})

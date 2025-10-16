from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event

from ..utils.pull_request_review import (
    apply_pull_request_review_filters,
    check_dismissal_message,
    check_dismissed_by,
    load_pull_request_review_payload,
)


class PullRequestReviewDismissedEvent(Event):
    """GitHub Pull Request Review Dismissed Event"""

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload, review, pull_request = load_pull_request_review_payload(request, expected_action="dismissed")
        apply_pull_request_review_filters(review, pull_request, parameters)
        check_dismissed_by(payload, parameters.get("dismissed_by"))
        check_dismissal_message(payload, parameters.get("dismissal_message_contains"))
        return Variables(variables={**payload})

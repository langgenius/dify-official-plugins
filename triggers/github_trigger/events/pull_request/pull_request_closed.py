from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event

from ..utils.pull_request import (
    apply_pull_request_common_filters,
    check_merged_state,
    load_pull_request_payload,
)


class PullRequestClosedEvent(Event):
    """GitHub Pull Request Closed Event"""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload, pull_request = load_pull_request_payload(request, expected_action="closed")
        apply_pull_request_common_filters(pull_request, parameters)
        check_merged_state(pull_request, parameters.get("merged"))
        return Variables(variables={**payload})

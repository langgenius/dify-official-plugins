from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event

from ..utils.pull_request import apply_pull_request_common_filters, load_pull_request_payload


class PullRequestEditedEvent(Event):
    """GitHub Pull Request Edited Event"""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload, pull_request = load_pull_request_payload(request, expected_action="edited")
        apply_pull_request_common_filters(pull_request, parameters)
        return Variables(variables={**payload})

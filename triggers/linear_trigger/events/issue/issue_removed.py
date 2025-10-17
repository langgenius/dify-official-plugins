from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class IssueRemovedEvent(Event):
    """
    Linear Issue Removed Event

    This event transforms Linear issue removed webhook events and extracts relevant
    information from the webhook payload to provide as variables to the workflow.
    """

    def _check_title_contains(self, issue_data: Mapping[str, Any], title_contains: str | None) -> None:
        """Check if issue title contains required keywords"""
        if not title_contains:
            return

        keywords = [keyword.strip().lower() for keyword in title_contains.split(",") if keyword.strip()]
        if not keywords:
            return

        title = (issue_data.get("title") or "").lower()
        if not any(keyword in title for keyword in keywords):
            raise EventIgnoreError()

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Transform Linear issue removed webhook event into structured Variables
        """
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        # Get issue data
        issue_data = payload.get("data")
        if not issue_data:
            raise ValueError("No issue data in payload")

        # Apply filters
        self._check_title_contains(issue_data, parameters.get("title_contains"))

        # Return full payload as variables
        return Variables(variables={**payload})

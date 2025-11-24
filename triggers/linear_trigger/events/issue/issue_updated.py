from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class IssueUpdatedEvent(Event):
    """
    Linear Issue Updated Event

    This event transforms Linear issue updated webhook events and extracts relevant
    information from the webhook payload to provide as variables to the workflow.
    """

    def _check_priority_filter(self, issue_data: Mapping[str, Any], priority_filter: str | None) -> None:
        """Check if issue priority matches the filter"""
        if not priority_filter:
            return

        allowed_priorities = []
        for p in priority_filter.split(","):
            p = p.strip()
            if p.isdigit():
                allowed_priorities.append(int(p))

        if not allowed_priorities:
            return

        priority = issue_data.get("priority", 0)
        if priority not in allowed_priorities:
            raise EventIgnoreError()

    def _check_state_filter(self, issue_data: Mapping[str, Any], state_filter: str | None) -> None:
        """Check if issue state matches the filter"""
        if not state_filter:
            return

        allowed_states = [s.strip().lower() for s in state_filter.split(",") if s.strip()]
        if not allowed_states:
            return

        # Check state name from state object
        state = issue_data.get("state", {})
        state_name = (state.get("name") or "").lower()

        if not state_name or state_name not in allowed_states:
            raise EventIgnoreError()

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

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any] | None = None) -> Variables:
        """
        Transform Linear issue updated webhook event into structured Variables
        """
        payload = payload or request.get_json()
        if not payload:
            raise ValueError("No payload received")

        # Get issue data
        issue_data = payload.get("data")
        if not issue_data:
            raise ValueError("No issue data in payload")

        # Apply all filters
        self._check_priority_filter(issue_data, parameters.get("priority_filter"))
        self._check_state_filter(issue_data, parameters.get("state_filter"))
        self._check_title_contains(issue_data, parameters.get("title_contains"))

        # Return full payload as variables
        return Variables(variables={**payload})

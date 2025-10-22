from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class IssueCreatedEvent(Event):
    """
    Linear Issue Created Event

    This event transforms Linear issue created webhook events and extracts relevant
    information from the webhook payload to provide as variables to the workflow.
    """

    def _check_state_filter(self, issue_data: Mapping[str, Any], state_filter: str | None) -> None:
        """Check if issue state matches the filter"""
        if not state_filter:
            return

        allowed_states = [s.strip() for s in state_filter.split(",") if s.strip()]
        if not allowed_states:
            return

        # Note: Linear sends stateId, not state name directly
        # For now, we check if stateId is in the filter
        # TODO: Might need to fetch state name from stateId via API
        state_id = issue_data.get("stateId")
        if not state_id or state_id not in allowed_states:
            raise EventIgnoreError()

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

    def _check_label_filter(self, issue_data: Mapping[str, Any], label_filter: str | None) -> None:
        """Check if issue has required labels"""
        if not label_filter:
            return

        required_label_names = [label.strip() for label in label_filter.split(",") if label.strip()]
        if not required_label_names:
            return

        # Linear sends labelIds, not label names
        # For basic filtering, check if any labelId is in the filter
        label_ids = issue_data.get("labelIds", [])
        if not label_ids:
            raise EventIgnoreError()

        # If label_ids exist but we need names, we'd need to fetch them via API
        # For now, check if any labelId matches the filter strings
        if not any(label_id in required_label_names for label_id in label_ids):
            raise EventIgnoreError()

    def _check_assignee_filter(self, issue_data: Mapping[str, Any], assignee_filter: str | None) -> None:
        """Check if issue is assigned to allowed users"""
        if not assignee_filter:
            return

        allowed_assignees = [assignee.strip() for assignee in assignee_filter.split(",") if assignee.strip()]
        if not allowed_assignees:
            return

        assignee_id = issue_data.get("assigneeId")
        if not assignee_id or assignee_id not in allowed_assignees:
            raise EventIgnoreError()

    def _check_project_filter(self, issue_data: Mapping[str, Any], project_filter: str | None) -> None:
        """Check if issue belongs to allowed projects"""
        if not project_filter:
            return

        allowed_projects = [project.strip() for project in project_filter.split(",") if project.strip()]
        if not allowed_projects:
            return

        project_id = issue_data.get("projectId")
        if not project_id or project_id not in allowed_projects:
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
        Transform Linear issue created webhook event into structured Variables
        """
        payload = payload or request.get_json()
        if not payload:
            raise ValueError("No payload received")

        # Get issue data
        issue_data = payload.get("data")
        if not issue_data:
            raise ValueError("No issue data in payload")

        # Apply all filters
        self._check_state_filter(issue_data, parameters.get("state_filter"))
        self._check_priority_filter(issue_data, parameters.get("priority_filter"))
        self._check_label_filter(issue_data, parameters.get("label_filter"))
        self._check_assignee_filter(issue_data, parameters.get("assignee_filter"))
        self._check_project_filter(issue_data, parameters.get("project_filter"))
        self._check_title_contains(issue_data, parameters.get("title_contains"))

        # Return full payload as variables
        return Variables(variables={**payload})

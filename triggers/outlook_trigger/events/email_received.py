import re
from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class EmailReceivedEvent(Event):
    """
    Outlook Email Received Event

    This event transforms Outlook email received webhook events and extracts relevant
    information from the webhook payload to provide as variables to the workflow.
    The payload includes an 'email' object with the email details.
    """

    def _check_assigned_to(self, payload: Mapping[str, Any], assigned_to_param: str | None) -> None:
        """Check if the sender matches the allowed users"""
        if not assigned_to_param:
            return

        allowed_assignees = [assignee.strip() for assignee in assigned_to_param.split(",") if assignee.strip()]
        if not allowed_assignees:
            return

        # The payload contains the assignee who was assigned
        assignee = payload.get("assignee", {})
        assignee_login = assignee.get("login", "")

        if assignee_login not in allowed_assignees:
            raise EventIgnoreError()

    def _check_title_pattern(self, issue: Mapping[str, Any], pattern: str | None) -> None:
        """Check if issue title matches the pattern"""
        if not pattern:
            return

        title = issue.get("title", "")
        if not re.match(pattern, title):
            raise EventIgnoreError()

    def _check_labels(self, issue: Mapping[str, Any], labels_param: str | None) -> None:
        """Check if issue has required labels"""
        if not labels_param:
            return

        required_labels = [label.strip() for label in labels_param.split(",") if label.strip()]
        if not required_labels:
            return

        issue_labels = [label.get("name") for label in issue.get("labels", [])]
        if not any(label in issue_labels for label in required_labels):
            raise EventIgnoreError()

    def _check_assigner(self, payload: Mapping[str, Any], assigner_param: str | None) -> None:
        """Check if the user who assigned the issue is in allowed list"""
        if not assigner_param:
            return

        allowed_assigners = [assigner.strip() for assigner in assigner_param.split(",") if assigner.strip()]
        if not allowed_assigners:
            return

        assigner = payload.get("sender", {}).get("login")
        if assigner not in allowed_assigners:
            raise EventIgnoreError()

    def _check_milestone(self, issue: Mapping[str, Any], milestone_param: str | None) -> None:
        """Check if issue milestone matches allowed milestones"""
        if not milestone_param:
            return

        allowed_milestones = [milestone.strip() for milestone in milestone_param.split(",") if milestone.strip()]
        if not allowed_milestones:
            return

        milestone = issue.get("milestone")
        if not milestone:
            raise EventIgnoreError()

        milestone_title = milestone.get("title")
        if not milestone_title or milestone_title not in allowed_milestones:
            raise EventIgnoreError()

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Transform GitHub issue assigned webhook event into structured Variables
        """
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        issue = payload.get("issue")
        if not issue:
            raise ValueError("No issue data in payload")

        # Apply all filters
        self._check_assigned_to(payload, parameters.get("assigned_to"))
        self._check_title_pattern(issue, parameters.get("title_pattern"))
        self._check_labels(issue, parameters.get("labels"))
        self._check_assigner(payload, parameters.get("assigner"))
        self._check_milestone(issue, parameters.get("milestone"))

        return Variables(variables={**payload})

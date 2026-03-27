from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class CommentCreatedEvent(Event):
    """
    Linear Comment Created Event

    This event transforms Linear comment created webhook events and extracts relevant
    information from the webhook payload to provide as variables to the workflow.
    """

    def _check_body_contains(self, comment_data: Mapping[str, Any], body_contains: str | None) -> None:
        """Check if comment body contains required keywords"""
        if not body_contains:
            return

        keywords = [keyword.strip().lower() for keyword in body_contains.split(",") if keyword.strip()]
        if not keywords:
            return

        body = (comment_data.get("body") or "").lower()
        if not any(keyword in body for keyword in keywords):
            raise EventIgnoreError()

    def _check_issue_only(self, comment_data: Mapping[str, Any], issue_only: bool) -> None:
        """Check if comment is on an issue when issue_only filter is enabled"""
        if not issue_only:
            return

        # Comment must have issueId to be considered an issue comment
        issue_id = comment_data.get("issueId")
        if not issue_id:
            raise EventIgnoreError()

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any] | None = None) -> Variables:
        """
        Transform Linear comment created webhook event into structured Variables
        """
        payload = payload or request.get_json()
        if not payload:
            raise ValueError("No payload received")

        # Get comment data
        comment_data = payload.get("data")
        if not comment_data:
            raise ValueError("No comment data in payload")

        # Apply filters
        self._check_body_contains(comment_data, parameters.get("body_contains"))
        self._check_issue_only(comment_data, parameters.get("issue_only", False))

        # Return full payload as variables
        return Variables(variables={**payload})

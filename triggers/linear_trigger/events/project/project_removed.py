from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class ProjectRemovedEvent(Event):
    """
    Linear Project Removed Event

    This event transforms Linear project removed webhook events and extracts relevant
    information from the webhook payload to provide as variables to the workflow.
    """

    def _check_name_contains(self, project_data: Mapping[str, Any], name_contains: str | None) -> None:
        """Check if project name contains required keywords"""
        if not name_contains:
            return

        keywords = [keyword.strip().lower() for keyword in name_contains.split(",") if keyword.strip()]
        if not keywords:
            return

        name = (project_data.get("name") or "").lower()
        if not any(keyword in name for keyword in keywords):
            raise EventIgnoreError()

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any] | None = None) -> Variables:
        """
        Transform Linear project removed webhook event into structured Variables
        """
        payload = payload or request.get_json()
        if not payload:
            raise ValueError("No payload received")

        # Get project data
        project_data = payload.get("data")
        if not project_data:
            raise ValueError("No project data in payload")

        # Apply filters
        self._check_name_contains(project_data, parameters.get("name_contains"))

        # Return full payload as variables
        return Variables(variables={**payload})

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class ProjectCreatedEvent(Event):
    """
    Linear Project Created Event

    This event transforms Linear project created webhook events and extracts relevant
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

    def _check_priority_filter(self, project_data: Mapping[str, Any], priority_filter: str | None) -> None:
        """Check if project priority matches the filter"""
        if not priority_filter:
            return

        allowed_priorities = []
        for p in priority_filter.split(","):
            p = p.strip()
            if p.isdigit():
                allowed_priorities.append(int(p))

        if not allowed_priorities:
            return

        priority = project_data.get("priority", 0)
        if priority not in allowed_priorities:
            raise EventIgnoreError()

    def _check_team_filter(self, project_data: Mapping[str, Any], team_filter: str | None) -> None:
        """Check if project belongs to allowed teams"""
        if not team_filter:
            return

        allowed_teams = [team.strip() for team in team_filter.split(",") if team.strip()]
        if not allowed_teams:
            return

        team_ids = project_data.get("teamIds", [])
        # Check if any of the project's teams is in the allowed list
        if not any(team_id in allowed_teams for team_id in team_ids):
            raise EventIgnoreError()

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Transform Linear project created webhook event into structured Variables
        """
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        # Get project data
        project_data = payload.get("data")
        if not project_data:
            raise ValueError("No project data in payload")

        # Apply filters
        self._check_name_contains(project_data, parameters.get("name_contains"))
        self._check_priority_filter(project_data, parameters.get("priority_filter"))
        self._check_team_filter(project_data, parameters.get("team_filter"))

        # Return full payload as variables
        return Variables(variables={**payload})

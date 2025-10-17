from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class CycleCreatedEvent(Event):
    """
    Linear Cycle Created Event

    This event transforms Linear cycle created webhook events and extracts relevant
    information from the webhook payload to provide as variables to the workflow.
    """

    def _check_name_contains(self, cycle_data: Mapping[str, Any], name_contains: str | None) -> None:
        """Check if cycle name contains required keywords"""
        if not name_contains:
            return

        keywords = [keyword.strip().lower() for keyword in name_contains.split(",") if keyword.strip()]
        if not keywords:
            return

        name = (cycle_data.get("name") or "").lower()
        if not any(keyword in name for keyword in keywords):
            raise EventIgnoreError()

    def _check_team_filter(self, cycle_data: Mapping[str, Any], team_filter: str | None) -> None:
        """Check if cycle belongs to allowed team"""
        if not team_filter:
            return

        team_id = cycle_data.get("teamId")
        if not team_id or team_id != team_filter.strip():
            raise EventIgnoreError()

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Transform Linear cycle created webhook event into structured Variables
        """
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        # Get cycle data
        cycle_data = payload.get("data")
        if not cycle_data:
            raise ValueError("No cycle data in payload")

        # Apply filters
        self._check_name_contains(cycle_data, parameters.get("name_contains"))
        self._check_team_filter(cycle_data, parameters.get("team_filter"))

        # Return full payload as variables
        return Variables(variables={**payload})

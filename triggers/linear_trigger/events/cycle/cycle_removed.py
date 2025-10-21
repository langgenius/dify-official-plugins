from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class CycleRemovedEvent(Event):
    """
    Linear Cycle Removed Event

    This event transforms Linear cycle removed webhook events and extracts relevant
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

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any] | None = None) -> Variables:
        """
        Transform Linear cycle removed webhook event into structured Variables
        """
        payload = payload or request.get_json()
        if not payload:
            raise ValueError("No payload received")

        # Get cycle data
        cycle_data = payload.get("data")
        if not cycle_data:
            raise ValueError("No cycle data in payload")

        # Apply filters
        self._check_name_contains(cycle_data, parameters.get("name_contains"))

        # Return full payload as variables
        return Variables(variables={**payload})

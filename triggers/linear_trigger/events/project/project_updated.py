from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class ProjectUpdatedEvent(Event):
    """
    Linear Project Updated Event

    This event transforms Linear project updated webhook events and extracts relevant
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

    def _check_status_changed(
        self,
        project_data: Mapping[str, Any],
        updated_from: Mapping[str, Any] | None,
        status_changed: bool,
    ) -> None:
        """Check if this update includes a status change"""
        if not status_changed:
            return

        # Linear exposes previous values of the changed fields in updatedFrom
        if not updated_from:
            raise EventIgnoreError()

        current_status_id = project_data.get("statusId")
        previous_status_id = updated_from.get("statusId")

        if previous_status_id is not None and previous_status_id != current_status_id:
            return

        current_status = project_data.get("status") or {}
        previous_status = updated_from.get("status") or {}

        if previous_status and any(
            previous_status.get(key) != current_status.get(key)
            for key in ("id", "type", "name")
        ):
            return

        for field in ("startedAt", "completedAt", "canceledAt"):
            if field in updated_from and updated_from.get(field) != project_data.get(field):
                return

        raise EventIgnoreError()

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        """
        Transform Linear project updated webhook event into structured Variables
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
        updated_from = payload.get("updatedFrom")
        status_changed_param = parameters.get("status_changed", False)
        if isinstance(status_changed_param, str):
            normalized = status_changed_param.strip().lower()
            status_changed_flag = normalized in {"true", "1", "yes", "on"}
        else:
            status_changed_flag = bool(status_changed_param)

        self._check_status_changed(
            project_data,
            updated_from if isinstance(updated_from, Mapping) else None,
            status_changed_flag,
        )

        # Return full payload as variables
        return Variables(variables={**payload})

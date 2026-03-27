from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class InitiativeRemovedEvent(Event):
    """Linear initiative removed webhook event."""

    @staticmethod
    def _parse_list(value: str | None) -> list[str]:
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    def _check_name_contains(self, data: Mapping[str, Any], name_contains: str | None) -> None:
        keywords = [keyword.lower() for keyword in self._parse_list(name_contains)]
        if not keywords:
            return

        name = (data.get("name") or "").lower()
        if not any(keyword in name for keyword in keywords):
            raise EventIgnoreError()

    def _check_status_filter(self, data: Mapping[str, Any], status_filter: str | None) -> None:
        allowed_statuses = [status.lower() for status in self._parse_list(status_filter)]
        if not allowed_statuses:
            return

        status = (data.get("status") or "").lower()
        if not status or status not in allowed_statuses:
            raise EventIgnoreError()

    def _check_owner_filter(self, data: Mapping[str, Any], owner_filter: str | None) -> None:
        allowed_owners = self._parse_list(owner_filter)
        if not allowed_owners:
            return

        owner_id = (data.get("ownerId") or "").strip()
        if not owner_id or owner_id not in allowed_owners:
            raise EventIgnoreError()

    def _check_health_filter(self, data: Mapping[str, Any], health_filter: str | None) -> None:
        allowed_health = [health.lower() for health in self._parse_list(health_filter)]
        if not allowed_health:
            return

        health = (data.get("health") or "").lower()
        if not health or health not in allowed_health:
            raise EventIgnoreError()

    def _check_project_filter(self, data: Mapping[str, Any], project_filter: str | None) -> None:
        allowed_projects = self._parse_list(project_filter)
        if not allowed_projects:
            return

        projects = data.get("projects") or []
        project_ids = [
            (project.get("id") or "").strip()
            for project in projects
            if isinstance(project, Mapping)
        ]
        if not any(project_id in allowed_projects for project_id in project_ids):
            raise EventIgnoreError()

    def _apply_filters(self, data: Mapping[str, Any], parameters: Mapping[str, Any]) -> None:
        self._check_name_contains(data, parameters.get("name_contains"))
        self._check_status_filter(data, parameters.get("status_filter"))
        self._check_owner_filter(data, parameters.get("owner_filter"))
        self._check_health_filter(data, parameters.get("health_filter"))
        self._check_project_filter(data, parameters.get("project_filter"))

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any] | None = None) -> Variables:
        payload = payload or request.get_json()
        if not payload:
            raise ValueError("No payload received")

        initiative_data = payload.get("data")
        if not initiative_data:
            raise ValueError("No initiative data in payload")

        self._apply_filters(initiative_data, parameters)
        return Variables(variables={**payload})

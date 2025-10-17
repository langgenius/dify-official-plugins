from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class ProjectUpdateCreatedEvent(Event):
    """Linear project update created webhook event."""

    @staticmethod
    def _parse_list_filter(value: str | None) -> list[str]:
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    def _check_body_contains(self, data: Mapping[str, Any], body_contains: str | None) -> None:
        keywords = [keyword.lower() for keyword in self._parse_list_filter(body_contains)]
        if not keywords:
            return

        body = (data.get("body") or "").lower()
        if not any(keyword in body for keyword in keywords):
            raise EventIgnoreError()

    def _check_health_filter(self, data: Mapping[str, Any], health_filter: str | None) -> None:
        allowed_health = [value.lower() for value in self._parse_list_filter(health_filter)]
        if not allowed_health:
            return

        health = (data.get("health") or "").lower()
        if not health or health not in allowed_health:
            raise EventIgnoreError()

    def _check_project_filter(self, data: Mapping[str, Any], project_filter: str | None) -> None:
        allowed_projects = self._parse_list_filter(project_filter)
        if not allowed_projects:
            return

        project_id = (data.get("projectId") or "").strip()
        if not project_id or project_id not in allowed_projects:
            raise EventIgnoreError()

    def _check_author_filter(self, data: Mapping[str, Any], author_filter: str | None) -> None:
        allowed_users = self._parse_list_filter(author_filter)
        if not allowed_users:
            return

        user_id = (data.get("userId") or "").strip()
        if not user_id or user_id not in allowed_users:
            raise EventIgnoreError()

    def _apply_filters(self, data: Mapping[str, Any], parameters: Mapping[str, Any]) -> None:
        self._check_body_contains(data, parameters.get("body_contains"))
        self._check_health_filter(data, parameters.get("health_filter"))
        self._check_project_filter(data, parameters.get("project_filter"))
        self._check_author_filter(data, parameters.get("author_filter"))

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        update_data = payload.get("data")
        if not update_data:
            raise ValueError("No project update data in payload")

        self._apply_filters(update_data, parameters)
        return Variables(variables={**payload})

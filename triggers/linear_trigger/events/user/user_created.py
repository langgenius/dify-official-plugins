from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class UserCreatedEvent(Event):
    """Linear user created webhook event."""

    @staticmethod
    def _parse_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "on"}
        return False

    @staticmethod
    def _parse_list(value: str | None) -> list[str]:
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    def _check_email_contains(self, data: Mapping[str, Any], email_contains: str | None) -> None:
        keywords = [keyword.lower() for keyword in self._parse_list(email_contains)]
        if not keywords:
            return

        email = (data.get("email") or "").lower()
        if not any(keyword in email for keyword in keywords):
            raise EventIgnoreError()

    def _check_active_only(self, data: Mapping[str, Any], active_only: Any) -> None:
        if not self._parse_bool(active_only):
            return

        if not data.get("active"):
            raise EventIgnoreError()

    def _check_admin_only(self, data: Mapping[str, Any], admin_only: Any) -> None:
        if not self._parse_bool(admin_only):
            return

        if not data.get("admin"):
            raise EventIgnoreError()

    def _check_guest_only(self, data: Mapping[str, Any], guest_only: Any) -> None:
        if not self._parse_bool(guest_only):
            return

        if not data.get("guest"):
            raise EventIgnoreError()

    def _check_exclude_apps(self, data: Mapping[str, Any], exclude_apps: Any) -> None:
        if not self._parse_bool(exclude_apps):
            return

        if data.get("app"):
            raise EventIgnoreError()

    def _apply_filters(self, data: Mapping[str, Any], parameters: Mapping[str, Any]) -> None:
        self._check_email_contains(data, parameters.get("email_contains"))
        self._check_active_only(data, parameters.get("active_only"))
        self._check_admin_only(data, parameters.get("admin_only"))
        self._check_guest_only(data, parameters.get("guest_only"))
        self._check_exclude_apps(data, parameters.get("exclude_app_users"))

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any] | None = None) -> Variables:
        payload = payload or request.get_json()
        if not payload:
            raise ValueError("No payload received")

        user_data = payload.get("data")
        if not user_data:
            raise ValueError("No user data in payload")

        self._apply_filters(user_data, parameters)
        return Variables(variables={**payload})

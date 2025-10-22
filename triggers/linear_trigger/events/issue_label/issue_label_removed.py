from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class IssueLabelRemovedEvent(Event):
    """Linear issue label removed webhook event."""

    @staticmethod
    def _parse_list_filter(value: str | None) -> list[str]:
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    @staticmethod
    def _parse_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "on"}
        return False

    def _check_name_contains(self, data: Mapping[str, Any], name_contains: str | None) -> None:
        keywords = [keyword.lower() for keyword in self._parse_list_filter(name_contains)]
        if not keywords:
            return

        name = (data.get("name") or "").lower()
        if not any(keyword in name for keyword in keywords):
            raise EventIgnoreError()

    def _check_color_filter(self, data: Mapping[str, Any], color_filter: str | None) -> None:
        allowed_colors = [color.lower() for color in self._parse_list_filter(color_filter)]
        if not allowed_colors:
            return

        color = (data.get("color") or "").lower()
        if not color or color not in allowed_colors:
            raise EventIgnoreError()

    def _check_team_filter(self, data: Mapping[str, Any], team_filter: str | None) -> None:
        allowed_team_ids = self._parse_list_filter(team_filter)
        if not allowed_team_ids:
            return

        team_id = (data.get("teamId") or "").strip()
        if not team_id or team_id not in allowed_team_ids:
            raise EventIgnoreError()

    def _check_group_only(self, data: Mapping[str, Any], group_only: Any) -> None:
        if not self._parse_bool(group_only):
            return

        if not data.get("isGroup", False):
            raise EventIgnoreError()

    def _apply_filters(self, data: Mapping[str, Any], parameters: Mapping[str, Any]) -> None:
        self._check_name_contains(data, parameters.get("name_contains"))
        self._check_color_filter(data, parameters.get("color_filter"))
        self._check_team_filter(data, parameters.get("team_filter"))
        self._check_group_only(data, parameters.get("group_only"))

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any] | None = None) -> Variables:
        payload = payload or request.get_json()
        if not payload:
            raise ValueError("No payload received")

        label_data = payload.get("data")
        if not label_data:
            raise ValueError("No issue label data in payload")

        self._apply_filters(label_data, parameters)
        return Variables(variables={**payload})

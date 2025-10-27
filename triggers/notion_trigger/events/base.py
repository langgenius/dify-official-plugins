from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError


class NotionBaseEvent():
    """Base class for Notion webhook events."""

    expected_type: str = ""

    def _parse_workspace_filter(self, workspace_filter: str | None) -> set[str]:
        if not workspace_filter:
            return set()
        return {value.strip() for value in workspace_filter.split(",") if value.strip()}

    def _check_workspace_filter(self, payload: Mapping[str, Any], workspace_filter: str | None) -> None:
        allowed = self._parse_workspace_filter(workspace_filter)
        if not allowed:
            return
        workspace_id = payload.get("workspace_id")
        if workspace_id not in allowed:
            raise EventIgnoreError()

    def _validate_type(self, payload: Mapping[str, Any]) -> None:
        if self.expected_type and payload.get("type") != self.expected_type:
            raise EventIgnoreError()

    def _on_event(
        self,
        request: Request,
        parameters: Mapping[str, Any],
        payload: Mapping[str, Any] | None = None,
    ) -> Variables:
        payload = payload or request.get_json()
        if not isinstance(payload, Mapping) or not payload:
            raise ValueError("No payload received")

        self._validate_type(payload)
        self._check_workspace_filter(payload, parameters.get("workspace_filter"))

        return Variables(variables={**payload})

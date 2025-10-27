from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class LabelUnifiedEvent(Event):
    """Unified Label event (created/edited/deleted)."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        allowed_actions = parameters.get("actions") or []
        action = payload.get("action")
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        label = payload.get("label")
        if not isinstance(label, Mapping):
            raise ValueError("No label in payload")

        self._check_name(label, parameters.get("name"))
        self._check_color(label, parameters.get("color"))

        return Variables(variables={**payload})

    def _check_name(self, label: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        names = {v.strip() for v in str(value).split(",") if v.strip()}
        if names and (label.get("name") or "") not in names:
            raise EventIgnoreError()

    def _check_color(self, label: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        colors = {v.strip().lower() for v in str(value).split(",") if v.strip()}
        color = (label.get("color") or "").lower()
        if colors and color not in colors:
            raise EventIgnoreError()

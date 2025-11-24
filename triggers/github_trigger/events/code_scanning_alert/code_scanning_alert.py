from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class CodeScanningAlertEvent(Event):
    """Unified GitHub Code Scanning Alert event with actions filter."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        # Actions: created, fixed, reopened, dismissed
        allowed_actions = parameters.get("actions") or []
        action = payload.get("action")
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        alert = payload.get("alert")
        if not isinstance(alert, Mapping):
            raise ValueError("No alert data in payload")

        self._check_severity(alert, parameters.get("severity"))
        self._check_state(alert, parameters.get("state"))
        self._check_rule_id(alert, parameters.get("rule_id"))
        self._check_tool_name(alert, parameters.get("tool_name"))
        self._check_branch(alert, parameters.get("branch"))

        return Variables(variables={**payload})

    def _check_severity(self, alert: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        sev = (alert.get("severity") or alert.get("rule", {}).get("security_severity_level") or "").lower()
        targets = {s.strip().lower() for s in str(value).split(",") if s.strip()}
        if targets and sev not in targets:
            raise EventIgnoreError()

    def _check_state(self, alert: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        state = (alert.get("state") or "").lower()
        targets = {s.strip().lower() for s in str(value).split(",") if s.strip()}
        if targets and state not in targets:
            raise EventIgnoreError()

    def _check_rule_id(self, alert: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        rid = str(alert.get("rule", {}).get("id") or "").strip()
        targets = {s.strip() for s in str(value).split(",") if s.strip()}
        if targets and rid not in targets:
            raise EventIgnoreError()

    def _check_tool_name(self, alert: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        tool = alert.get("tool") or {}
        name = str(tool.get("name") or tool.get("guid") or "").strip()
        targets = {s.strip() for s in str(value).split(",") if s.strip()}
        if targets and name not in targets:
            raise EventIgnoreError()

    def _check_branch(self, alert: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        branches = {s.strip() for s in str(value).split(",") if s.strip()}
        if not branches:
            return
        ref = (alert.get("most_recent_instance") or {}).get("ref") or alert.get("ref") or ""
        # Convert refs/heads/main -> main
        branch = ref.split("/", 2)[-1] if ref.startswith("refs/heads/") else ref
        if branch not in branches:
            raise EventIgnoreError()

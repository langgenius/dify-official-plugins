from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class DependabotAlertEvent(Event):
    """Unified Dependabot security alert event."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        allowed_actions = parameters.get("actions") or []
        action = payload.get("action")
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        alert = payload.get("alert")
        if not isinstance(alert, Mapping):
            raise ValueError("No alert in payload")

        self._check_severity(alert, parameters.get("severity"))
        self._check_state(alert, parameters.get("state"))
        self._check_ecosystem(alert, parameters.get("ecosystem"))
        self._check_package(alert, parameters.get("package"))
        self._check_manifest(alert, parameters.get("manifest"))

        return Variables(variables={**payload})

    def _check_severity(self, alert: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        advisory = alert.get("security_advisory") or {}
        sev = (advisory.get("severity") or alert.get("security_severity_level") or "").lower()
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

    def _check_ecosystem(self, alert: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        advisory = alert.get("security_vulnerability") or {}
        eco = ((advisory.get("package") or {}).get("ecosystem") or "").lower()
        targets = {s.strip().lower() for s in str(value).split(",") if s.strip()}
        if targets and eco not in targets:
            raise EventIgnoreError()

    def _check_package(self, alert: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        name = (((alert.get("security_vulnerability") or {}).get("package") or {}).get("name") or "").lower()
        targets = {s.strip().lower() for s in str(value).split(",") if s.strip()}
        if targets and name not in targets:
            raise EventIgnoreError()

    def _check_manifest(self, alert: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        manifest = (alert.get("manifest") or "").lower()
        targets = {s.strip().lower() for s in str(value).split(",") if s.strip()}
        if targets and manifest not in targets:
            raise EventIgnoreError()

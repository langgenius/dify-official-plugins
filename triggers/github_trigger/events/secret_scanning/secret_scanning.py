from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class SecretScanningEvent(Event):
    """Unified Secret Scanning events across subtypes (alert/location/scan)."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        event_type = (request.headers.get("X-GitHub-Event") or "").lower()
        subtype = self._infer_subtype(event_type)

        # Subtypes filter
        allowed_subtypes = parameters.get("subtypes") or []
        if allowed_subtypes and subtype not in allowed_subtypes:
            raise EventIgnoreError()

        # Actions differ by subtype; apply generic actions filter if provided
        allowed_actions = parameters.get("actions") or []
        action = (payload.get("action") or "").lower()
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        # Generic filters
        self._check_secret_type(payload, parameters.get("secret_type"))
        self._check_severity(payload, parameters.get("severity"))
        self._check_branch(payload, parameters.get("branch"))

        return Variables(variables={"subtype": subtype, **payload})

    def _infer_subtype(self, event_type: str) -> str:
        if event_type == "secret_scanning_alert":
            return "alert"
        if event_type == "secret_scanning_alert_location":
            return "alert_location"
        if event_type == "secret_scanning_scan":
            return "scan"
        return "unknown"

    def _check_secret_type(self, payload: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        types = {s.strip().lower() for s in str(value).split(",") if s.strip()}
        if not types:
            return
        alert = payload.get("alert") or {}
        stype = (alert.get("secret_type") or alert.get("secret_type_display_name") or "").lower()
        if stype and stype not in types:
            raise EventIgnoreError()

    def _check_severity(self, payload: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        levels = {s.strip().lower() for s in str(value).split(",") if s.strip()}
        if not levels:
            return
        alert = payload.get("alert") or {}
        sev = (alert.get("severity") or "").lower()
        if sev and sev not in levels:
            raise EventIgnoreError()

    def _check_branch(self, payload: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        branches = {s.strip() for s in str(value).split(",") if s.strip()}
        if not branches:
            return
        ref = (payload.get("alert") or {}).get("most_recent_instance", {}).get("ref") or ""
        branch = ref.split("/", 2)[-1] if ref.startswith("refs/heads/") else ref
        if branch and branch not in branches:
            raise EventIgnoreError()


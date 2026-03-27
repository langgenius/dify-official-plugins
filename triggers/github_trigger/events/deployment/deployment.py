from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class DeploymentEvent(Event):
    """Unified Deployment event (primarily 'created')."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        allowed_actions = parameters.get("actions") or []
        action = payload.get("action")
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        deployment = payload.get("deployment")
        if not isinstance(deployment, Mapping):
            raise ValueError("No deployment in payload")

        self._check_environment(deployment, parameters.get("environment"))
        self._check_ref(deployment, parameters.get("ref"))
        self._check_creator(payload, parameters.get("creator"))
        return Variables(variables={**payload})

    def _check_environment(self, deployment: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        env = (deployment.get("environment") or "").strip()
        targets = {s.strip() for s in str(value).split(",") if s.strip()}
        if targets and env not in targets:
            raise EventIgnoreError()

    def _check_ref(self, deployment: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        ref = (deployment.get("ref") or "").strip()
        targets = {s.strip() for s in str(value).split(",") if s.strip()}
        if targets and ref not in targets:
            raise EventIgnoreError()

    def _check_creator(self, payload: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        creator = (payload.get("sender", {}) or {}).get("login")
        targets = {s.strip() for s in str(value).split(",") if s.strip()}
        if targets and creator not in targets:
            raise EventIgnoreError()

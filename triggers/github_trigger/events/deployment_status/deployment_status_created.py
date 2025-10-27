from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class DeploymentStatusCreatedEvent(Event):
    """GitHub Deployment Status Created Event"""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        if payload.get("action") != "created":
            raise EventIgnoreError()

        status = payload.get("deployment_status")
        deployment = payload.get("deployment")
        if not isinstance(status, Mapping) or not isinstance(deployment, Mapping):
            raise ValueError("Missing deployment or deployment_status in payload")

        self._check_environment(deployment, parameters.get("environment"))
        self._check_state(status, parameters.get("state"))
        self._check_ref(deployment, parameters.get("ref"))
        self._check_creator(payload, parameters.get("creator"))

        return Variables(variables={**payload})

    def _check_environment(self, deployment: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        envs = [v.strip() for v in value.split(",") if v.strip()]
        if not envs:
            return
        env = (deployment.get("environment") or "").strip()
        if env not in envs:
            raise EventIgnoreError()

    def _check_state(self, status: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        states = [v.strip().lower() for v in value.split(",") if v.strip()]
        if not states:
            return
        current = (status.get("state") or "").lower()
        if current not in states:
            raise EventIgnoreError()

    def _check_ref(self, deployment: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        refs = [v.strip() for v in value.split(",") if v.strip()]
        if not refs:
            return
        current = (deployment.get("ref") or "").strip()
        if current not in refs:
            raise EventIgnoreError()

    def _check_creator(self, payload: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        users = [v.strip() for v in value.split(",") if v.strip()]
        if not users:
            return
        creator = payload.get("sender", {}).get("login")
        if creator not in users:
            raise EventIgnoreError()

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class WorkflowRunCompletedEvent(Event):
    """GitHub Workflow Run Completed Event"""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        if payload.get("action") != "completed":
            raise EventIgnoreError()

        run = payload.get("workflow_run")
        if not isinstance(run, Mapping):
            raise ValueError("No workflow_run data in payload")

        self._check_name(run, parameters.get("workflow_name"))
        self._check_branch(run, parameters.get("branch"))
        self._check_conclusion(run, parameters.get("conclusion"))
        self._check_actor(payload, parameters.get("actor"))

        return Variables(variables={**payload})

    def _check_name(self, run: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        names = [v.strip() for v in value.split(",") if v.strip()]
        if not names:
            return
        name = run.get("name") or run.get("display_title")
        if name not in names:
            raise EventIgnoreError()

    def _check_branch(self, run: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        branches = [v.strip() for v in value.split(",") if v.strip()]
        if not branches:
            return
        if run.get("head_branch") not in branches:
            raise EventIgnoreError()

    def _check_conclusion(self, run: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        allowed = [v.strip().lower() for v in value.split(",") if v.strip()]
        if not allowed:
            return
        conclusion = (run.get("conclusion") or "").lower()
        if conclusion not in allowed:
            raise EventIgnoreError()

    def _check_actor(self, payload: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        users = [v.strip() for v in value.split(",") if v.strip()]
        if not users:
            return
        actor_login = payload.get("sender", {}).get("login")
        if actor_login not in users:
            raise EventIgnoreError()

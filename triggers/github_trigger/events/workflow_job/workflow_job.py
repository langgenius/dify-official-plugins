from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class WorkflowJobUnifiedEvent(Event):
    """Unified Workflow Job event (queued/in_progress/completed)."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        allowed_actions = parameters.get("actions") or []
        action = payload.get("action")
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        job = payload.get("workflow_job")
        if not isinstance(job, Mapping):
            raise ValueError("No workflow_job in payload")

        self._check_workflow_name(job, parameters.get("workflow_name"))
        self._check_job_name(job, parameters.get("job_name"))
        self._check_branch(job, parameters.get("branch"))
        if action == "completed":
            self._check_conclusion(job, parameters.get("conclusion"))
        self._check_runner_labels(job, parameters.get("runner_labels"))
        self._check_actor(payload, parameters.get("actor"))

        return Variables(variables={**payload})

    def _check_workflow_name(self, job: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        names = {v.strip() for v in str(value).split(",") if v.strip()}
        if not names:
            return
        if job.get("workflow_name") not in names:
            raise EventIgnoreError()

    def _check_job_name(self, job: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        names = {v.strip() for v in str(value).split(",") if v.strip()}
        if not names:
            return
        if job.get("name") not in names:
            raise EventIgnoreError()

    def _check_branch(self, job: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        branches = {v.strip() for v in str(value).split(",") if v.strip()}
        if not branches:
            return
        if job.get("head_branch") not in branches:
            raise EventIgnoreError()

    def _check_conclusion(self, job: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        allowed = {v.strip().lower() for v in str(value).split(",") if v.strip()}
        if not allowed:
            return
        conclusion = (job.get("conclusion") or "").lower()
        if conclusion and conclusion not in allowed:
            raise EventIgnoreError()

    def _check_runner_labels(self, job: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        targets = {v.strip() for v in str(value).split(",") if v.strip()}
        if not targets:
            return
        labels = job.get("labels") or []
        current = {str(label).strip() for label in labels}
        if not any(t in current for t in targets):
            raise EventIgnoreError()

    def _check_actor(self, payload: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        users = {v.strip() for v in str(value).split(",") if v.strip()}
        if not users:
            return
        actor_login = (payload.get("sender") or {}).get("login")
        if actor_login not in users:
            raise EventIgnoreError()

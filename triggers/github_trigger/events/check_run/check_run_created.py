from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class CheckRunCreatedEvent(Event):
    """GitHub Check Run Created Event"""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        if payload.get("action") != "created":
            raise EventIgnoreError()

        run = payload.get("check_run")
        if not isinstance(run, Mapping):
            raise ValueError("No check_run data in payload")

        self._check_name(run, parameters.get("check_name"))
        self._check_branch(run, parameters.get("branch"))
        self._check_app_slug(run, parameters.get("app_slug"))
        self._check_actor(payload, parameters.get("actor"))

        return Variables(variables={**payload})

    def _check_name(self, run: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        names = [v.strip() for v in value.split(",") if v.strip()]
        if not names:
            return
        name = (run.get("name") or "").strip()
        if name not in names:
            raise EventIgnoreError()

    def _check_branch(self, run: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        branches = [v.strip() for v in value.split(",") if v.strip()]
        if not branches:
            return
        # Prefer PR head ref if available
        pr_list = run.get("pull_requests") or []
        branch: str | None = None
        for pr in pr_list:
            head = pr.get("head") if isinstance(pr, Mapping) else None
            if isinstance(head, Mapping):
                branch = head.get("ref")
                if branch:
                    break
        if not branch:
            # Fallback: not always present in check_run
            suite = run.get("check_suite") if isinstance(run, Mapping) else None
            if isinstance(suite, Mapping):
                branch = suite.get("head_branch")
        if branch not in branches:
            raise EventIgnoreError()

    def _check_app_slug(self, run: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        slugs = [v.strip() for v in value.split(",") if v.strip()]
        if not slugs:
            return
        app = run.get("app") or {}
        slug = (app.get("slug") if isinstance(app, Mapping) else None) or ""
        if slug not in slugs:
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

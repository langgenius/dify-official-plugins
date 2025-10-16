from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class CheckSuiteCompletedEvent(Event):
    """GitHub Check Suite Completed Event"""

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        if payload.get("action") != "completed":
            raise EventIgnoreError()

        suite = payload.get("check_suite")
        if not isinstance(suite, Mapping):
            raise ValueError("No check_suite data in payload")

        self._check_conclusion(suite, parameters.get("conclusion"))
        self._check_branch(suite, parameters.get("branch"))
        self._check_app_slug(suite, parameters.get("app_slug"))

        return Variables(variables={**payload})

    def _check_conclusion(self, suite: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        allowed = [v.strip().lower() for v in value.split(",") if v.strip()]
        if not allowed:
            return
        conclusion = (suite.get("conclusion") or "").lower()
        if conclusion not in allowed:
            raise EventIgnoreError()

    def _check_branch(self, suite: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        branches = [v.strip() for v in value.split(",") if v.strip()]
        if not branches:
            return
        head_branch = suite.get("head_branch")
        if head_branch not in branches:
            raise EventIgnoreError()

    def _check_app_slug(self, suite: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        slugs = [v.strip() for v in value.split(",") if v.strip()]
        if not slugs:
            return
        app = suite.get("app") or {}
        slug = (app.get("slug") if isinstance(app, Mapping) else None) or ""
        if slug not in slugs:
            raise EventIgnoreError()


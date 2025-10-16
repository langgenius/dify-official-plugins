from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class StatusEvent(Event):
    """GitHub Commit Status event (legacy CI)."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        self._check_context(payload, parameters.get("context"))
        self._check_state(payload, parameters.get("state"))
        self._check_branch(payload, parameters.get("branch"))
        self._check_target_url(payload, parameters.get("target_url_contains"))

        return Variables(variables={**payload})

    def _check_context(self, payload: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        ctx = (payload.get("context") or "").strip()
        targets = {s.strip() for s in str(value).split(",") if s.strip()}
        if targets and ctx not in targets:
            raise EventIgnoreError()

    def _check_state(self, payload: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        st = (payload.get("state") or "").lower()
        targets = {s.strip().lower() for s in str(value).split(",") if s.strip()}
        if targets and st not in targets:
            raise EventIgnoreError()

    def _check_branch(self, payload: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        branches = {s.strip() for s in str(value).split(",") if s.strip()}
        if not branches:
            return
        for br in payload.get("branches") or []:
            name = (br.get("name") or "").strip()
            if name in branches:
                return
        raise EventIgnoreError()

    def _check_target_url(self, payload: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        substrings = {s.strip().lower() for s in str(value).split(",") if s.strip()}
        if not substrings:
            return
        url = (payload.get("target_url") or "").lower()
        if not any(s in url for s in substrings):
            raise EventIgnoreError()


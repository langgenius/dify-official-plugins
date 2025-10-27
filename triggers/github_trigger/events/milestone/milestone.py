from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class MilestoneUnifiedEvent(Event):
    """Unified Milestone event (created/opened/closed/edited/deleted)."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        allowed_actions = parameters.get("actions") or []
        action = payload.get("action")
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        milestone = payload.get("milestone")
        if not isinstance(milestone, Mapping):
            raise ValueError("No milestone in payload")

        self._check_title(milestone, parameters.get("title"))
        self._check_state(milestone, parameters.get("state"))
        self._check_due_on(milestone, parameters.get("due_on"))
        self._check_creator(payload, parameters.get("creator"))

        return Variables(variables={**payload})

    def _check_title(self, milestone: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        names = {v.strip() for v in str(value).split(",") if v.strip()}
        title = (milestone.get("title") or "").strip()
        if names and title not in names:
            raise EventIgnoreError()

    def _check_state(self, milestone: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        state = (milestone.get("state") or "").lower()
        states = {v.strip().lower() for v in str(value).split(",") if v.strip()}
        if states and state not in states:
            raise EventIgnoreError()

    def _check_due_on(self, milestone: Mapping[str, Any], value: str | None) -> None:
        # value could be a date string or comma list; for simplicity compare string equality if provided
        if not value:
            return
        targets = {v.strip() for v in str(value).split(",") if v.strip()}
        due_on = (milestone.get("due_on") or "").strip()
        if targets and due_on not in targets:
            raise EventIgnoreError()

    def _check_creator(self, payload: Mapping[str, Any], value: str | None) -> None:
        if not value:
            return
        users = {v.strip() for v in str(value).split(",") if v.strip()}
        creator = (payload.get("sender") or {}).get("login")
        if users and creator not in users:
            raise EventIgnoreError()

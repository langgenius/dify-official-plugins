from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class MemberUnifiedEvent(Event):
    """Unified Member event (added/edited/removed)."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        allowed_actions = parameters.get("actions") or []
        action = payload.get("action")
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        member = payload.get("member")
        if not isinstance(member, Mapping):
            raise ValueError("No member in payload")

        filter_login = parameters.get("member")
        if filter_login:
            users = {v.strip() for v in str(filter_login).split(",") if v.strip()}
            if users and (member.get("login") or "") not in users:
                raise EventIgnoreError()

        return Variables(variables={**payload})


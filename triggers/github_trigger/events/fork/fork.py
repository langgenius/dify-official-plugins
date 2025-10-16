from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class ForkEvent(Event):
    """Unified Fork event."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        forker = (payload.get("sender") or {}).get("login")
        allowed = parameters.get("forker")
        if allowed:
            users = {u.strip() for u in str(allowed).split(",") if u.strip()}
            if users and forker not in users:
                raise EventIgnoreError()

        return Variables(variables={**payload})


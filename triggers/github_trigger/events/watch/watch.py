from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class WatchEvent(Event):
    """Unified Watch event (typically 'started')."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        allowed_actions = parameters.get("actions") or []
        action = payload.get("action") or "started"
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        watcher = (payload.get("sender") or {}).get("login")
        allowed = parameters.get("watcher")
        if allowed:
            users = {u.strip() for u in str(allowed).split(",") if u.strip()}
            if users and watcher not in users:
                raise EventIgnoreError()

        return Variables(variables={**payload})

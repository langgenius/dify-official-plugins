from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class SecurityAndAnalysisUnifiedEvent(Event):
    """Unified security_and_analysis settings changes event."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        changes = payload.get("changes")

        settings_filter = parameters.get("settings")
        if settings_filter:
            wanted = {v.strip() for v in str(settings_filter).split(",") if v.strip()}
            found = set()
            if isinstance(changes, Mapping):
                found.update(changes.keys())
            if wanted and not (wanted & found):
                raise EventIgnoreError()

        return Variables(variables={**payload})


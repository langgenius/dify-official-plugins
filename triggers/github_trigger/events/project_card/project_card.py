from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class ProjectCardUnifiedEvent(Event):
    """Unified Project Card event (created/edited/deleted/moved/converted)."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        allowed_actions = parameters.get("actions") or []
        action = payload.get("action")
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        card = payload.get("project_card")
        if not isinstance(card, Mapping):
            raise ValueError("No project_card in payload")

        note_contains = parameters.get("note_contains")
        if note_contains:
            note = (card.get("note") or "").lower()
            keywords = [v.strip().lower() for v in str(note_contains).split(",") if v.strip()]
            if keywords and not any(k in note for k in keywords):
                raise EventIgnoreError()

        return Variables(variables={**payload})

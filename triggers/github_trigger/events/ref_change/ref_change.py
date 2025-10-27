from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class RefChangeEvent(Event):
    """Unified create/delete for branch and tag."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        event_type = (request.headers.get("X-GitHub-Event") or "").lower()
        action = "created" if event_type == "create" else "deleted"

        # Filter by event types
        allowed_types = parameters.get("event_types") or []
        if allowed_types and event_type not in allowed_types:
            raise EventIgnoreError()

        ref_type = (payload.get("ref_type") or "").lower()
        allowed_ref_type = parameters.get("ref_type")
        if allowed_ref_type and ref_type != allowed_ref_type:
            raise EventIgnoreError()

        ref = payload.get("ref") or ""
        allowed_refs = parameters.get("ref_names")
        if allowed_refs:
            names = {s.strip() for s in str(allowed_refs).split(",") if s.strip()}
            if names and ref not in names:
                raise EventIgnoreError()

        return Variables(variables={"action": action, **payload})

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class MergeGroupUnifiedEvent(Event):
    """Unified Merge Group event (merge queue)."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        allowed_actions = parameters.get("actions") or []
        action = payload.get("action")
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        mg = payload.get("merge_group")
        if not isinstance(mg, Mapping):
            # Some deliveries might not wrap under 'merge_group', be permissive
            mg = {}

        base_ref = parameters.get("base_ref")
        if base_ref:
            names = {v.strip() for v in str(base_ref).split(",") if v.strip()}
            if names and (mg.get("base_ref") or "") not in names:
                raise EventIgnoreError()

        head_sha = parameters.get("head_sha")
        if head_sha:
            allowed = {v.strip().lower() for v in str(head_sha).split(",") if v.strip()}
            sha = (mg.get("head_sha") or "").lower()
            if allowed and sha not in allowed:
                raise EventIgnoreError()

        return Variables(variables={**payload})

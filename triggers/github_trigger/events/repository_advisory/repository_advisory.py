from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class RepositoryAdvisoryUnifiedEvent(Event):
    """Unified repository_advisory event (published/updated/withdrawn)."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        allowed_actions = parameters.get("actions") or []
        action = payload.get("action")
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        advisory = payload.get("repository_advisory")
        if not isinstance(advisory, Mapping):
            raise ValueError("No repository_advisory in payload")

        severity_filter = parameters.get("severity")
        if severity_filter:
            allowed = {v.strip().lower() for v in str(severity_filter).split(",") if v.strip()}
            sev = (advisory.get("severity") or "").lower()
            if allowed and sev not in allowed:
                raise EventIgnoreError()

        ghsa_filter = parameters.get("ghsa_id")
        if ghsa_filter:
            allowed = {v.strip().upper() for v in str(ghsa_filter).split(",") if v.strip()}
            ghsa = (advisory.get("ghsa_id") or "").upper()
            if allowed and ghsa not in allowed:
                raise EventIgnoreError()

        return Variables(variables={**payload})


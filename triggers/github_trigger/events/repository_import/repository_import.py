from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class RepositoryImportUnifiedEvent(Event):
    """Unified Repository Import event (status changes)."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        status_filter = parameters.get("status")
        import_obj = payload.get("import")
        if isinstance(import_obj, Mapping) and status_filter:
            allowed = {v.strip().lower() for v in str(status_filter).split(",") if v.strip()}
            status = (import_obj.get("status") or "").lower()
            if allowed and status not in allowed:
                raise EventIgnoreError()

        vcs_filter = parameters.get("vcs")
        if isinstance(import_obj, Mapping) and vcs_filter:
            allowed_vcs = {v.strip().lower() for v in str(vcs_filter).split(",") if v.strip()}
            vcs = (import_obj.get("vcs") or "").lower()
            if allowed_vcs and vcs not in allowed_vcs:
                raise EventIgnoreError()

        return Variables(variables={**payload})


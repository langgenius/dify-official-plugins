from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class PageBuildEvent(Event):
    """GitHub Pages page_build event (built/errored)."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        build = payload.get("build")
        if not isinstance(build, Mapping):
            raise ValueError("No build in payload")

        status_filter = parameters.get("status")
        status = (build.get("status") or "").lower()
        if status_filter:
            allowed = {v.strip().lower() for v in str(status_filter).split(",") if v.strip()}
            if allowed and status not in allowed:
                raise EventIgnoreError()

        return Variables(variables={**payload})


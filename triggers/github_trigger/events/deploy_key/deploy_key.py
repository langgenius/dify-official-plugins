from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class DeployKeyUnifiedEvent(Event):
    """Unified Deploy Key event (created/deleted)."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        allowed_actions = parameters.get("actions") or []
        action = payload.get("action")
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        key = payload.get("key") or payload.get("deploy_key")
        if not isinstance(key, Mapping):
            raise ValueError("No deploy key in payload")

        title_filter = parameters.get("title")
        if title_filter:
            titles = {v.strip() for v in str(title_filter).split(",") if v.strip()}
            if titles and (key.get("title") or "") not in titles:
                raise EventIgnoreError()

        fingerprint = parameters.get("fingerprint")
        if fingerprint:
            fps = {v.strip().lower() for v in str(fingerprint).split(",") if v.strip()}
            if fps and (str(key.get("fingerprint") or "").lower()) not in fps:
                raise EventIgnoreError()

        return Variables(variables={**payload})

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class RegistryPackageUnifiedEvent(Event):
    """Unified Registry Package event (Container registry etc.)."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        allowed_actions = parameters.get("actions") or []
        action = payload.get("action")
        if allowed_actions and action not in allowed_actions:
            raise EventIgnoreError()

        registry_package = payload.get("registry_package")
        if not isinstance(registry_package, Mapping):
            raise ValueError("No registry_package in payload")

        name_filter = parameters.get("name")
        if name_filter:
            names = {v.strip() for v in str(name_filter).split(",") if v.strip()}
            if names and (registry_package.get("name") or "") not in names:
                raise EventIgnoreError()

        package_type = parameters.get("package_type")
        if package_type:
            allowed_types = {v.strip().lower() for v in str(package_type).split(",") if v.strip()}
            ptype = (registry_package.get("package_type") or "").lower()
            if allowed_types and ptype not in allowed_types:
                raise EventIgnoreError()

        return Variables(variables={**payload})

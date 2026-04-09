from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class CustomPropertyValuesUnifiedEvent(Event):
    """Unified Custom Property Values event."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        props = payload.get("property_values")
        if props is None:
            # forward payload even if missing; schema tolerates nulls
            pass

        name_filter = parameters.get("property_name")
        if name_filter:
            names = {v.strip() for v in str(name_filter).split(",") if v.strip()}
            matched = False
            if isinstance(props, list):
                for p in props:
                    if (p or {}).get("property_name") in names:
                        matched = True
                        break
            if names and not matched:
                raise EventIgnoreError()

        return Variables(variables={**payload})

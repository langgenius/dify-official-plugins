from collections.abc import Mapping
from typing import Any
from werkzeug import Request
from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event

class CustomerNeedUpdatedEvent(Event):
    def _check_title_contains(self, data: Mapping[str, Any], title_contains: str | None) -> None:
        if not title_contains:
            return
        keywords = [k.strip().lower() for k in title_contains.split(",") if k.strip()]
        if not keywords:
            return
        value = (data.get("title") or "").lower()
        if not any(keyword in value for keyword in keywords):
            raise EventIgnoreError()

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")
        data = payload.get("data")
        if not data:
            raise ValueError("No customer need data in payload")
        self._check_title_contains(data, parameters.get("title_contains"))
        return Variables(variables={**payload})

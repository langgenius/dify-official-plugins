from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event
from provider.discord import _extract_convenience_ids


class DiscordWebhookEvent(Event):
    """Generic Discord Webhook Event."""

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        if payload:
            return Variables(variables={**payload})
        return Variables(variables={**self._normalize_from_request(request)})

    def _normalize_from_request(self, request: Request) -> dict[str, Any]:
        raw_payload = request.get_json(force=True)
        event = raw_payload.get("event") if isinstance(raw_payload.get("event"), Mapping) else {}
        data = event.get("data") if isinstance(event.get("data"), Mapping) else {}

        variables: dict[str, Any] = {
            "version": raw_payload.get("version"),
            "application_id": raw_payload.get("application_id"),
            "webhook_type": raw_payload.get("type"),
            "event_type": event.get("type"),
            "timestamp": event.get("timestamp"),
            "data": data,
            "raw_payload": raw_payload,
        }

        convenience_ids = _extract_convenience_ids(data, event.get("type"))
        variables.update({key: value for key, value in convenience_ids.items() if value is not None})
        return variables

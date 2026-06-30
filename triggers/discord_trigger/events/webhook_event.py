from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.interfaces.trigger import Event


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

        user = data.get("user") if isinstance(data.get("user"), Mapping) else {}
        guild = data.get("guild") if isinstance(data.get("guild"), Mapping) else {}
        entitlement = data.get("entitlement") if isinstance(data.get("entitlement"), Mapping) else data
        lobby = data.get("lobby") if isinstance(data.get("lobby"), Mapping) else data
        message = data.get("message") if isinstance(data.get("message"), Mapping) else data

        convenience_ids = {
            "user_id": user.get("id") or data.get("user_id"),
            "guild_id": guild.get("id") or data.get("guild_id"),
            "entitlement_id": entitlement.get("id"),
            "lobby_id": lobby.get("lobby_id") or lobby.get("id"),
            "message_id": message.get("id") or data.get("message_id"),
        }
        variables.update({key: value for key, value in convenience_ids.items() if value is not None})
        return variables

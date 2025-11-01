from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError

from .catalog_data import EVENT_CATALOG

_MESSAGE_TOPIC_TO_CHANNEL_TYPE: dict[str, str] = {
    "message.app.home": "app_home",
    "message.channels": "channel",
    "message.groups": "group",
    "message.im": "im",
    "message.mpim": "mpim",
}

_MESSAGE_IGNORE_SUBTYPES = {
    "message_changed",
    "message_deleted",
    "message_replied",
    "thread_broadcast",
    "channel_join",
    "channel_leave",
}


class CatalogSlackEvent:
    """Generic Slack event transformer backed by the generated catalog."""

    EVENT_KEY: str = ""

    def _get_metadata(self) -> Mapping[str, Any]:
        if not self.EVENT_KEY:
            raise ValueError("EVENT_KEY must be defined on CatalogSlackEvent subclasses")
        try:
            metadata = EVENT_CATALOG[self.EVENT_KEY]
        except KeyError as exc:
            raise ValueError(f"Unknown Slack event key: {self.EVENT_KEY}") from exc
        return metadata

    def _sanitize(self, value: Any) -> Any:
        if value is None:
            return ""
        if isinstance(value, Mapping):
            return {str(key): self._sanitize(val) for key, val in value.items()}
        if isinstance(value, list):
            return [self._sanitize(item) for item in value]
        return value

    def _ensure_list(self, value: Any) -> list[Any]:
        if isinstance(value, list):
            return value
        if value in ("", None):
            return []
        return [value]

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        metadata = self._get_metadata()

        payload = request.get_json(silent=True) or {}
        event = payload.get("event")
        if not isinstance(event, Mapping):
            raise ValueError("Slack event payload is missing the event body")

        event_type = str(event.get("type") or "")
        expected_event_type = str(metadata.get("event_type") or "")

        if expected_event_type == "message":
            if event_type != "message":
                raise EventIgnoreError()
            subtype = str(event.get("subtype") or "")
            if subtype and subtype in _MESSAGE_IGNORE_SUBTYPES:
                raise EventIgnoreError()
            expected_channel_type = _MESSAGE_TOPIC_TO_CHANNEL_TYPE.get(metadata["topic"], "")
            if expected_channel_type:
                channel_type = str(event.get("channel_type") or "")
                if channel_type != expected_channel_type:
                    raise EventIgnoreError()
        else:
            if event_type != expected_event_type:
                raise EventIgnoreError()

        sanitized_payload = self._sanitize(payload)
        sanitized_event = self._sanitize(event)

        channel_type = str(sanitized_event.get("channel_type") or "")
        if expected_event_type != "message" and not channel_type:
            channel_type = ""

        authorizations = self._ensure_list(sanitized_payload.get("authorizations", []))
        authed_users = self._ensure_list(sanitized_payload.get("authed_users", []))
        authed_teams = self._ensure_list(sanitized_payload.get("authed_teams", []))

        scopes_required = self._ensure_list(metadata.get("scopes_required", []))
        tokens_allowed = self._ensure_list(metadata.get("tokens_allowed", []))
        tags = self._ensure_list(metadata.get("tags", []))

        variables: dict[str, Any] = {
            "event_topic": str(metadata.get("topic") or ""),
            "event_type": event_type or expected_event_type,
            "event_id": str(payload.get("event_id") or ""),
            "team_id": str(payload.get("team_id") or ""),
            "api_app_id": str(payload.get("api_app_id") or ""),
            "event_time": str(payload.get("event_time") or ""),
            "event_context": str(payload.get("event_context") or ""),
            "authorizations": authorizations,
            "authed_users": authed_users,
            "authed_teams": authed_teams,
            "is_ext_shared_channel": bool(sanitized_event.get("is_ext_shared_channel", False)),
            "channel_type": channel_type,
            "summary": str(metadata.get("summary") or metadata.get("label") or ""),
            "doc_url": str(metadata.get("doc_url") or ""),
            "scopes_required": scopes_required,
            "tokens_allowed": tokens_allowed,
            "tags": tags,
            "event_body": sanitized_event,
            "raw_payload": sanitized_payload,
        }

        return Variables(variables=variables)

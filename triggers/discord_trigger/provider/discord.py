from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey
from werkzeug import Request, Response

from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.entities.trigger import EventDispatch, Subscription, UnsubscribeResult
from dify_plugin.errors.trigger import SubscriptionError, TriggerDispatchError, TriggerValidationError
from dify_plugin.interfaces.trigger import Trigger, TriggerSubscriptionConstructor


DISCORD_PING_TYPE = 0
DISCORD_EVENT_TYPE = 1
DISCORD_EVENT_NAME = "webhook_event"


DISCORD_WEBHOOK_EVENT_TYPES = {
    "APPLICATION_AUTHORIZED",
    "APPLICATION_DEAUTHORIZED",
    "ENTITLEMENT_CREATE",
    "ENTITLEMENT_UPDATE",
    "ENTITLEMENT_DELETE",
    "QUEST_USER_ENROLLMENT",
    "LOBBY_MESSAGE_CREATE",
    "LOBBY_MESSAGE_UPDATE",
    "LOBBY_MESSAGE_DELETE",
    "GAME_DIRECT_MESSAGE_CREATE",
    "GAME_DIRECT_MESSAGE_UPDATE",
    "GAME_DIRECT_MESSAGE_DELETE",
}


class DiscordTrigger(Trigger):
    """Dispatch Discord Webhook Events."""

    def _dispatch_event(self, subscription: Subscription, request: Request) -> EventDispatch:
        public_key = str(subscription.properties.get("application_public_key") or "").strip()
        if not public_key:
            raise TriggerDispatchError("Discord application public key is missing from subscription properties")

        raw_body = request.get_data(cache=True, as_text=False)
        self._verify_signature(public_key=public_key, request=request, raw_body=raw_body)
        payload = self._parse_payload(raw_body)

        webhook_type = payload.get("type")
        response = self._empty_response()

        if webhook_type == DISCORD_PING_TYPE:
            return EventDispatch(events=[], response=response, payload=payload)

        if webhook_type != DISCORD_EVENT_TYPE:
            raise TriggerDispatchError(f"Unsupported Discord webhook type: {webhook_type}")

        event = payload.get("event")
        if not isinstance(event, Mapping):
            raise TriggerDispatchError("Discord webhook event payload is missing event object")

        event_type = event.get("type")
        if not isinstance(event_type, str) or not event_type:
            raise TriggerDispatchError("Discord webhook event payload is missing event.type")

        if not self._event_type_allowed(subscription, event_type):
            return EventDispatch(events=[], response=response, payload=self._normalize_payload(payload))

        return EventDispatch(
            events=[DISCORD_EVENT_NAME],
            response=response,
            payload=self._normalize_payload(payload),
        )

    def _verify_signature(self, *, public_key: str, request: Request, raw_body: bytes) -> None:
        signature = request.headers.get("X-Signature-Ed25519")
        if not signature:
            raise TriggerValidationError("Missing X-Signature-Ed25519 header")

        timestamp = request.headers.get("X-Signature-Timestamp")
        if not timestamp:
            raise TriggerValidationError("Missing X-Signature-Timestamp header")

        try:
            verify_key = VerifyKey(bytes.fromhex(public_key))
            verify_key.verify(timestamp.encode("utf-8") + raw_body, bytes.fromhex(signature))
        except ValueError as exc:
            raise TriggerValidationError("Invalid Discord public key or signature encoding") from exc
        except BadSignatureError as exc:
            raise TriggerValidationError("Invalid Discord request signature") from exc

    @staticmethod
    def _parse_payload(raw_body: bytes) -> Mapping[str, Any]:
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as exc:
            raise TriggerDispatchError(f"Failed to parse Discord webhook payload: {exc}") from exc

        if not isinstance(payload, Mapping):
            raise TriggerDispatchError("Discord webhook payload must be a JSON object")
        if not payload:
            raise TriggerDispatchError("Empty Discord webhook payload")
        return payload

    @staticmethod
    def _event_type_allowed(subscription: Subscription, event_type: str) -> bool:
        allowed_event_types = subscription.properties.get("event_types") or []
        if not allowed_event_types:
            return True
        return event_type in set(str(item) for item in allowed_event_types)

    @staticmethod
    def _normalize_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
        event = payload.get("event") if isinstance(payload.get("event"), Mapping) else {}
        data = event.get("data") if isinstance(event.get("data"), Mapping) else {}

        normalized: dict[str, Any] = {
            "version": payload.get("version"),
            "application_id": payload.get("application_id"),
            "webhook_type": payload.get("type"),
            "event_type": event.get("type"),
            "timestamp": event.get("timestamp"),
            "data": data,
            "raw_payload": dict(payload),
        }

        for key, value in _extract_convenience_ids(data).items():
            if value is not None:
                normalized[key] = value

        return normalized

    @staticmethod
    def _empty_response() -> Response:
        return Response(response="", status=204, content_type="application/json")


class DiscordSubscriptionConstructor(TriggerSubscriptionConstructor):
    """Store manual Discord Webhook Events subscription metadata."""

    def _create_subscription(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> Subscription:
        public_key = str(parameters.get("application_public_key") or "").strip()
        if not public_key:
            raise SubscriptionError("application_public_key is required", error_code="MISSING_PUBLIC_KEY")

        try:
            bytes.fromhex(public_key)
        except ValueError as exc:
            raise SubscriptionError("application_public_key must be a hex string", error_code="INVALID_PUBLIC_KEY") from exc

        event_types = _normalize_event_types(parameters.get("event_types"))

        return Subscription(
            expires_at=-1,
            endpoint=endpoint,
            parameters=parameters,
            properties={
                "application_public_key": public_key,
                "event_types": event_types,
                "managed_by": "manual",
            },
        )

    def _delete_subscription(
        self,
        subscription: Subscription,
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> UnsubscribeResult:
        return UnsubscribeResult(
            success=True,
            message="Subscription removed. Remove the Webhook Events URL from Discord Developer Portal manually.",
        )

    def _refresh_subscription(
        self,
        subscription: Subscription,
        credentials: Mapping[str, Any],
        credential_type: CredentialType,
    ) -> Subscription:
        return Subscription(
            expires_at=-1,
            endpoint=subscription.endpoint,
            parameters=subscription.parameters,
            properties=subscription.properties,
        )


def _normalize_event_types(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        candidates = [item.strip() for item in value.split(",") if item.strip()]
    elif isinstance(value, list):
        candidates = [str(item).strip() for item in value if str(item).strip()]
    else:
        raise SubscriptionError("event_types must be a list or comma-separated string", error_code="INVALID_EVENT_TYPES")

    invalid = [item for item in candidates if item not in DISCORD_WEBHOOK_EVENT_TYPES]
    if invalid:
        raise SubscriptionError(
            f"Unsupported Discord webhook event types: {', '.join(invalid)}",
            error_code="INVALID_EVENT_TYPES",
        )
    return candidates


def _extract_convenience_ids(data: Mapping[str, Any]) -> dict[str, Any]:
    user = data.get("user") if isinstance(data.get("user"), Mapping) else {}
    guild = data.get("guild") if isinstance(data.get("guild"), Mapping) else {}
    entitlement = data.get("entitlement") if isinstance(data.get("entitlement"), Mapping) else data
    lobby = data.get("lobby") if isinstance(data.get("lobby"), Mapping) else data
    message = data.get("message") if isinstance(data.get("message"), Mapping) else data

    return {
        "user_id": user.get("id") or data.get("user_id"),
        "guild_id": guild.get("id") or data.get("guild_id"),
        "entitlement_id": entitlement.get("id"),
        "lobby_id": lobby.get("lobby_id") or lobby.get("id"),
        "message_id": message.get("id") or data.get("message_id"),
    }

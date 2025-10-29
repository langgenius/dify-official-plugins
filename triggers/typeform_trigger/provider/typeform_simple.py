"""Typeform trigger provider implementation."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Mapping
from typing import Any

from werkzeug import Request, Response

from dify_plugin.entities.trigger import EventDispatch, Subscription, UnsubscribeResult
from dify_plugin.errors.trigger import SubscriptionError, TriggerDispatchError, TriggerValidationError
from dify_plugin.interfaces.trigger import Trigger, TriggerSubscriptionConstructor

_SUPPORTED_EVENT_TYPES: dict[str, str] = {
    "form_response": "form_response_received",
}


class TypeformTrigger(Trigger):
    """Dispatch Typeform webhook events."""

    def _dispatch_event(self, subscription: Subscription, request: Request) -> EventDispatch:
        raw_body = request.get_data()
        if raw_body is None:
            raise TriggerDispatchError("Missing request body")

        secret = subscription.properties.get("webhook_secret")
        if secret:
            self._verify_signature(secret=secret, request=request, raw_body=raw_body)

        payload = self._parse_payload(raw_body)

        event_type = payload.get("event_type")
        if not isinstance(event_type, str):
            raise TriggerDispatchError("Missing event_type in payload")

        mapped_event = _SUPPORTED_EVENT_TYPES.get(event_type)
        if mapped_event is None:
            raise TriggerDispatchError(f"Unsupported Typeform event_type: {event_type}")

        form_id_filter = subscription.properties.get("form_id")
        if form_id_filter:
            form_response = payload.get("form_response")
            target_form_id = None
            if isinstance(form_response, Mapping):
                target_form_id = form_response.get("form_id")

            if target_form_id != form_id_filter:
                response = Response(response='{"status": "ignored"}', status=200, mimetype="application/json")
                return EventDispatch(events=[], response=response, payload=payload)

        response = Response(response='{"status": "ok"}', status=200, mimetype="application/json")
        return EventDispatch(events=[mapped_event], response=response, payload=payload)

    @staticmethod
    def _parse_payload(raw_body: bytes) -> Mapping[str, Any]:
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as exc:  # pragma: no cover - unexpected JSON errors
            raise TriggerDispatchError(f"Failed to parse JSON payload: {exc}") from exc

        if not isinstance(payload, Mapping):
            raise TriggerDispatchError("Payload must be a JSON object")
        if not payload:
            raise TriggerDispatchError("Empty payload")
        return payload

    @staticmethod
    def _verify_signature(*, secret: str, request: Request, raw_body: bytes) -> None:
        header = request.headers.get("Typeform-Signature")
        if not header:
            raise TriggerValidationError("Missing Typeform-Signature header")

        prefix = "sha256="
        if not header.startswith(prefix):
            raise TriggerValidationError("Unsupported signature format")

        digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
        expected = prefix + base64.b64encode(digest).decode("ascii")

        if not hmac.compare_digest(header, expected):
            raise TriggerValidationError("Invalid webhook signature")


class TypeformSubscriptionConstructor(TriggerSubscriptionConstructor):
    """Store Typeform webhook subscription metadata."""

    def _create_subscription(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        credentials: Mapping[str, Any],
        credential_type,
    ) -> Subscription:
        form_id = parameters.get("form_id") or None
        webhook_secret = parameters.get("webhook_secret") or None

        if webhook_secret and not isinstance(webhook_secret, str):
            raise SubscriptionError("webhook_secret must be a string", error_code="invalid_secret")

        if form_id and not isinstance(form_id, str):
            raise SubscriptionError("form_id must be a string", error_code="invalid_form_id")

        return Subscription(
            expires_at=-1,
            endpoint=endpoint,
            parameters=parameters,
            properties={
                "form_id": form_id,
                "webhook_secret": webhook_secret,
            },
        )

    def _delete_subscription(
        self,
        subscription: Subscription,
        credentials: Mapping[str, Any],
        credential_type,
    ) -> UnsubscribeResult:
        # Webhooks are managed directly in Typeform; nothing to delete programmatically.
        return UnsubscribeResult(success=True, message="Subscription deleted")

    def _refresh_subscription(
        self,
        subscription: Subscription,
        credentials: Mapping[str, Any],
        credential_type,
    ) -> Subscription:
        # Webhooks do not expire automatically.
        return subscription


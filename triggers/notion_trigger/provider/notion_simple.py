"""Notion trigger provider.

This provider handles signature verification for Notion webhooks and maps
Notion event type strings (e.g. ``page.created``) to internal event names
(e.g. ``page_created``).

Subscriptions are created manually inside the Notion integration settings, so
the constructor simply stores the verification token (used for signature
validation) and optional event filters.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from typing import Any

from werkzeug import Request, Response

from dify_plugin.entities import I18nObject, ParameterOption
from dify_plugin.entities.trigger import EventDispatch, Subscription, UnsubscribeResult
from dify_plugin.errors.trigger import (
    SubscriptionError,
    TriggerDispatchError,
    TriggerValidationError,
)
from dify_plugin.interfaces.trigger import Trigger, TriggerSubscriptionConstructor

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SUPPORTED_EVENT_TYPES = [
    "page.created",
    "page.deleted",
    "page.undeleted",
    "page.content_updated",
    "page.moved",
    "page.properties_updated",
    "page.locked",
    "page.unlocked",
    "database.created",
    "database.content_updated",
    "database.deleted",
    "database.undeleted",
    "database.moved",
    "database.schema_updated",
    "data_source.created",
    "data_source.deleted",
    "data_source.undeleted",
    "data_source.moved",
    "data_source.content_updated",
    "data_source.schema_updated",
    "comment.created",
    "comment.updated",
    "comment.deleted",
]


# ---------------------------------------------------------------------------
# Trigger implementation
# ---------------------------------------------------------------------------

class NotionTrigger(Trigger):
    """Dispatch Notion webhook events."""

    def _dispatch_event(self, subscription: Subscription, request: Request) -> EventDispatch:
        raw_body = request.get_data()
        if raw_body is None:
            raise TriggerDispatchError("Missing request body")

        payload = self._parse_payload(request)

        # Handle the initial verification ping – payload only contains the token.
        if payload.keys() == {"verification_token"}:
            response = Response(response='{"status": "ok"}', status=200, mimetype="application/json")
            return EventDispatch(events=[], response=response, payload=payload)

        verification_token = subscription.properties.get("verification_token")
        if verification_token:
            self._validate_signature(request=request, raw_body=raw_body, verification_token=verification_token)

        event_type = payload.get("type")
        if not event_type:
            raise TriggerDispatchError("Missing event type in payload")

        # If subscription requested filtering, enforce it.
        allowed_events: list[str] | None = subscription.properties.get("event_types")
        if allowed_events and event_type not in allowed_events:
            response = Response(response='{"status": "ignored"}', status=200, mimetype="application/json")
            return EventDispatch(events=[], response=response, payload=payload)

        event_name = event_type.replace(".", "_")
        response = Response(response='{"status": "ok"}', status=200, mimetype="application/json")
        return EventDispatch(events=[event_name], response=response, payload=payload)

    @staticmethod
    def _parse_payload(request: Request) -> Mapping[str, Any]:
        try:
            payload = request.get_json(force=True)
        except Exception as exc:  # pragma: no cover - werkzeug raises BadRequest
            raise TriggerDispatchError(f"Failed to parse JSON payload: {exc}") from exc

        if not isinstance(payload, Mapping):
            raise TriggerDispatchError("Payload must be a JSON object")
        if not payload:
            raise TriggerDispatchError("Empty payload")
        return payload

    @staticmethod
    def _validate_signature(request: Request, raw_body: bytes, verification_token: str) -> None:
        """Validate ``X-Notion-Signature`` header."""
        header = request.headers.get("X-Notion-Signature")
        if not header:
            raise TriggerValidationError("Missing X-Notion-Signature header")

        prefix = "sha256="
        if not header.startswith(prefix):
            raise TriggerValidationError("Unsupported signature format")

        expected = hmac.new(verification_token.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(header[len(prefix):], expected):
            raise TriggerValidationError("Invalid webhook signature")


# ---------------------------------------------------------------------------
# Subscription constructor
# ---------------------------------------------------------------------------

class NotionSubscriptionConstructor(TriggerSubscriptionConstructor):
    """Store verification token and optional event filters."""

    def _create_subscription(
        self,
        endpoint: str,
        parameters: Mapping[str, Any],
        credentials: Mapping[str, Any],
        credential_type,
    ) -> Subscription:
        verification_token = parameters.get("verification_token")
        if not verification_token:
            raise SubscriptionError("verification_token is required", error_code="missing_verification_token")

        event_types_param = parameters.get("event_types")
        if isinstance(event_types_param, str):
            raw_event_types = [
                value.strip() for value in event_types_param.split(",") if value and value.strip()
            ]
        elif isinstance(event_types_param, list):
            raw_event_types = event_types_param
        else:
            raw_event_types = []

        # Ensure types are valid strings from supported list
        filtered_types: list[str] = [
            event_type for event_type in raw_event_types if event_type in _SUPPORTED_EVENT_TYPES
        ]

        return Subscription(
            expires_at=-1,
            endpoint=endpoint,
            parameters=parameters,
            properties={
                "verification_token": verification_token,
                "event_types": filtered_types or None,
            },
        )

    def _delete_subscription(
        self,
        subscription: Subscription,
        credentials: Mapping[str, Any],
        credential_type,
    ) -> UnsubscribeResult:
        # Nothing to delete on Notion's side (manual subscription management).
        return UnsubscribeResult(success=True, message="Subscription deleted")

    def _refresh_subscription(
        self,
        subscription: Subscription,
        credentials: Mapping[str, Any],
        credential_type,
    ) -> Subscription:
        # Subscriptions do not expire automatically; return as-is.
        return subscription

    def _fetch_parameter_options(
        self,
        parameter: str,
        credentials: Mapping[str, Any],
        credential_type,
    ) -> list[ParameterOption]:
        if parameter != "event_types":
            return []

        return [
            ParameterOption(value=event_type, label=I18nObject(en_US=event_type.replace(".", " → ")))
            for event_type in _SUPPORTED_EVENT_TYPES
        ]

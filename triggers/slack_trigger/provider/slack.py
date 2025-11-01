from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Mapping
from typing import Any

from events.catalog_data import EVENT_CATALOG
from werkzeug import Request, Response

from dify_plugin.entities.trigger import EventDispatch, Subscription
from dify_plugin.errors.trigger import (
    TriggerDispatchError,
    TriggerValidationError,
)
from dify_plugin.interfaces.trigger import Trigger

MESSAGE_CHANNEL_EVENT_KEYS: dict[str, str] = {
    "app_home": "message_app_home",
    "channel": "message_channels",
    "group": "message_groups",
    "im": "message_im",
    "mpim": "message_mpim",
}

MESSAGE_IGNORED_SUBTYPES = {
    "message_changed",
    "message_deleted",
    "message_replied",
    "thread_broadcast",
    "channel_join",
    "channel_leave",
}

EVENT_KEY_BY_TYPE: dict[str, str] = {
    str(metadata.get("event_type")): event_key
    for event_key, metadata in EVENT_CATALOG.items()
    if metadata.get("event_type") != "message"
}


class SlackTrigger(Trigger):
    """Trigger implementation for Slack event webhooks."""

    _VERSION = "v0"
    _MAX_SIGNATURE_AGE = 60 * 5  # five minutes

    def _dispatch_event(self, subscription: Subscription, request: Request) -> EventDispatch:
        signing_secret = str(subscription.properties.get("signing_secret") or "")
        if not signing_secret:
            raise TriggerDispatchError("Slack signing secret is missing from subscription properties")

        if request.headers.get("X-Slack-Retry-Num"):
            return EventDispatch(
                events=[],
                response=Response(response="{}", status=200, mimetype="application/json"),
            )

        payload, response = self._parse_request(signing_secret=signing_secret, request=request)
        dispatch_event = self._determine_event(subscription=subscription, payload=payload)

        events: list[str] = []
        if dispatch_event:
            events.append(dispatch_event)

        return EventDispatch(events=events, response=response)

    def _parse_request(self, signing_secret: str, request: Request) -> tuple[Mapping[str, Any], Response]:
        body_bytes = request.get_data(cache=True, as_text=False)
        timestamp_header = request.headers.get("X-Slack-Request-Timestamp")
        if not timestamp_header:
            raise TriggerValidationError("Missing Slack timestamp header")

        try:
            timestamp = int(timestamp_header)
        except ValueError as exc:
            raise TriggerValidationError("Invalid Slack timestamp header") from exc

        current_time = int(time.time())
        if abs(current_time - timestamp) > self._MAX_SIGNATURE_AGE:
            raise TriggerValidationError("Slack request timestamp is outside the allowed tolerance")

        signature = request.headers.get("X-Slack-Signature")
        if not signature:
            raise TriggerValidationError("Missing Slack signature header")

        try:
            body_text = body_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TriggerDispatchError("Slack payload must be UTF-8 encoded") from exc

        expected_signature = self._build_signature(
            signing_secret=signing_secret,
            timestamp=timestamp_header,
            body=body_text,
        )
        if not hmac.compare_digest(signature, expected_signature):
            raise TriggerValidationError("Invalid Slack signature")

        try:
            payload = json.loads(body_text)
        except json.JSONDecodeError as exc:
            raise TriggerDispatchError("Failed to decode Slack payload") from exc

        if payload.get("type") == "url_verification":
            challenge = payload.get("challenge")
            if not challenge:
                raise TriggerDispatchError("Slack URL verification payload missing challenge")
            return payload, Response(challenge, mimetype="text/plain", status=200)

        return payload, Response(response="{}", status=200, mimetype="application/json")

    def _determine_event(self, subscription: Subscription, payload: Mapping[str, Any]) -> str:
        if payload.get("type") != "event_callback":
            return ""

        event = payload.get("event")
        if not isinstance(event, Mapping):
            raise TriggerDispatchError("Slack payload missing event body")

        event_type = str(event.get("type") or "")

        if event_type == "message":
            subtype = str(event.get("subtype") or "")
            if subtype and subtype in MESSAGE_IGNORED_SUBTYPES:
                return ""
            channel_type = str(event.get("channel_type") or "")
            event_key = MESSAGE_CHANNEL_EVENT_KEYS.get(channel_type)
            if event_key:
                return event_key if event_key in EVENT_CATALOG else ""
            return "message" if "message" in EVENT_CATALOG else ""

        event_key = EVENT_KEY_BY_TYPE.get(event_type)
        if event_key:
            return event_key

        return event_type if event_type in EVENT_CATALOG else ""

    def _build_signature(self, signing_secret: str, timestamp: str, body: str) -> str:
        sig_basestring = f"{self._VERSION}:{timestamp}:{body}"
        digest = hmac.new(signing_secret.encode("utf-8"), sig_basestring.encode("utf-8"), hashlib.sha256)
        return f"{self._VERSION}={digest.hexdigest()}"

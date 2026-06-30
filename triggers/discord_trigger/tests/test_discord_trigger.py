import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from nacl.signing import SigningKey
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from events.webhook_event import DiscordWebhookEvent
from provider.discord import DiscordSubscriptionConstructor, DiscordTrigger
from dify_plugin.entities.provider_config import CredentialType
from dify_plugin.errors.trigger import SubscriptionError, TriggerDispatchError, TriggerValidationError


def _request(payload, signing_key=None, timestamp=None, signature_override=None):
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if signing_key is not None:
        timestamp = timestamp or str(int(time.time()))
        signature = signing_key.sign(timestamp.encode("utf-8") + body).signature.hex()
        headers["X-Signature-Timestamp"] = timestamp
        headers["X-Signature-Ed25519"] = signature_override or signature

    builder = EnvironBuilder(method="POST", path="/discord", data=body, headers=headers)
    return Request(builder.get_environ())


def _subscription(public_key, event_types=None):
    return SimpleNamespace(
        properties={
            "application_public_key": public_key,
            "event_types": event_types or [],
        }
    )


def _keypair():
    signing_key = SigningKey.generate()
    public_key = signing_key.verify_key.encode().hex()
    return signing_key, public_key


def _trigger():
    trigger = object.__new__(DiscordTrigger)
    trigger.runtime = SimpleNamespace()
    return trigger


def _event():
    event = object.__new__(DiscordWebhookEvent)
    event.runtime = SimpleNamespace()
    return event


def _constructor():
    constructor = object.__new__(DiscordSubscriptionConstructor)
    constructor.runtime = SimpleNamespace()
    return constructor


def test_create_subscription_stores_public_key_and_event_filter():
    _, public_key = _keypair()

    subscription = _constructor()._create_subscription(
        "https://example.test/discord",
        {
            "application_public_key": public_key,
            "event_types": ["APPLICATION_AUTHORIZED"],
        },
        {},
        CredentialType.UNAUTHORIZED,
    )

    assert subscription.endpoint == "https://example.test/discord"
    assert subscription.properties["application_public_key"] == public_key
    assert subscription.properties["event_types"] == ["APPLICATION_AUTHORIZED"]
    assert subscription.properties["managed_by"] == "manual"


def test_create_subscription_rejects_unknown_event_type():
    _, public_key = _keypair()

    with pytest.raises(SubscriptionError, match="Unsupported Discord webhook event types"):
        _constructor()._create_subscription(
            "https://example.test/discord",
            {
                "application_public_key": public_key,
                "event_types": ["MESSAGE_CREATE"],
            },
            {},
            CredentialType.UNAUTHORIZED,
        )


def test_valid_signed_ping_returns_204_and_no_events():
    signing_key, public_key = _keypair()
    request = _request({"version": 1, "application_id": "app_1", "type": 0}, signing_key)

    dispatch = _trigger()._dispatch_event(_subscription(public_key), request)

    assert dispatch.events == []
    assert dispatch.response.status_code == 204
    assert dispatch.response.get_data() == b""


def test_invalid_signature_fails_validation():
    signing_key, public_key = _keypair()
    request = _request(
        {"version": 1, "application_id": "app_1", "type": 0},
        signing_key,
        signature_override="00" * 64,
    )

    with pytest.raises(TriggerValidationError, match="Invalid Discord request signature"):
        _trigger()._dispatch_event(_subscription(public_key), request)


def test_missing_signature_headers_fail_validation():
    _, public_key = _keypair()
    request = _request({"version": 1, "application_id": "app_1", "type": 0})

    with pytest.raises(TriggerValidationError, match="Missing X-Signature-Ed25519 header"):
        _trigger()._dispatch_event(_subscription(public_key), request)


def test_valid_event_dispatches_webhook_event_with_normalized_payload():
    signing_key, public_key = _keypair()
    payload = {
        "version": 1,
        "application_id": "app_1",
        "type": 1,
        "event": {
            "type": "APPLICATION_AUTHORIZED",
            "timestamp": "2026-06-30T00:00:00+00:00",
            "data": {
                "user": {"id": "user_1"},
                "guild": {"id": "guild_1"},
                "scopes": ["applications.commands"],
            },
        },
    }
    request = _request(payload, signing_key)

    dispatch = _trigger()._dispatch_event(_subscription(public_key), request)

    assert dispatch.events == ["webhook_event"]
    assert dispatch.response.status_code == 204
    assert dispatch.payload["event_type"] == "APPLICATION_AUTHORIZED"
    assert dispatch.payload["user_id"] == "user_1"
    assert dispatch.payload["guild_id"] == "guild_1"
    assert dispatch.payload["raw_payload"] == payload


def test_event_type_filter_ignores_unselected_events():
    signing_key, public_key = _keypair()
    request = _request(
        {
            "version": 1,
            "application_id": "app_1",
            "type": 1,
            "event": {
                "type": "APPLICATION_DEAUTHORIZED",
                "timestamp": "2026-06-30T00:00:00+00:00",
                "data": {"user": {"id": "user_1"}},
            },
        },
        signing_key,
    )

    dispatch = _trigger()._dispatch_event(
        _subscription(public_key, event_types=["APPLICATION_AUTHORIZED"]),
        request,
    )

    assert dispatch.events == []
    assert dispatch.response.status_code == 204
    assert dispatch.payload["event_type"] == "APPLICATION_DEAUTHORIZED"


def test_malformed_json_raises_dispatch_error():
    signing_key, public_key = _keypair()
    body = b"{not-json"
    timestamp = str(int(time.time()))
    signature = signing_key.sign(timestamp.encode("utf-8") + body).signature.hex()
    request = Request(
        EnvironBuilder(
            method="POST",
            path="/discord",
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Signature-Timestamp": timestamp,
                "X-Signature-Ed25519": signature,
            },
        ).get_environ()
    )

    with pytest.raises(TriggerDispatchError, match="Failed to parse Discord webhook payload"):
        _trigger()._dispatch_event(_subscription(public_key), request)


def test_webhook_event_outputs_normalized_variables_from_payload():
    payload = {
        "version": 1,
        "application_id": "app_1",
        "webhook_type": 1,
        "event_type": "LOBBY_MESSAGE_CREATE",
        "timestamp": "2026-06-30T00:00:00+00:00",
        "data": {"lobby_id": "lobby_1", "message": {"id": "message_1"}},
        "lobby_id": "lobby_1",
        "message_id": "message_1",
        "raw_payload": {"type": 1},
    }

    variables = _event()._on_event(_request({}, None), {}, payload)

    assert variables.variables == payload

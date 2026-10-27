from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import httpx
import pytest
from werkzeug.test import EnvironBuilder

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dify_plugin.entities.provider_config import CredentialType  # noqa: E402
from dify_plugin.entities.trigger import Subscription  # noqa: E402
from dify_plugin.errors.trigger import (  # noqa: E402
    EventIgnoreError,
    SubscriptionError,
    TriggerProviderCredentialValidationError,
    TriggerValidationError,
)

from events.ticket.ticket_comment_created import TicketCommentCreatedEvent  # noqa: E402
from events.ticket.ticket_status_changed import TicketStatusChangedEvent  # noqa: E402
from events.utils import normalize_subdomain  # noqa: E402
from provider.zendesk import (  # noqa: E402
    EVENT_TYPE_MAPPING,
    ZendeskSubscriptionConstructor,
    ZendeskTrigger,
)

TICKET = {
    "id": "342757",
    "status": "OPEN",
    "priority": None,
    "subject": "Login broken",
    "tags": None,
}


def _comment_payload(body: str, *, is_public: bool = False, is_staff: bool = True) -> dict:
    return {
        "type": "zen:event-type:ticket.comment_added",
        "detail": TICKET,
        "event": {
            "comment": {
                "id": "8659716087550",
                "body": body,
                "is_public": is_public,
                "author": {"id": "1", "name": "Agent", "is_staff": is_staff},
            }
        },
    }


def _request(payload: dict, headers: dict | None = None):
    return EnvironBuilder(method="POST", data=json.dumps(payload), headers=headers or {}).get_request()


def _event_runtime(subdomain: str = "acme"):
    return SimpleNamespace(subscription=SimpleNamespace(properties={"subdomain": subdomain}), credentials=None)


def _response(status: int, body: dict | None = None, method: str = "POST") -> httpx.Response:
    request = httpx.Request(method, "https://acme.zendesk.com/api/v2/webhooks")
    if body is None:
        return httpx.Response(status, content=b"", request=request)
    return httpx.Response(status, json=body, request=request)


@pytest.mark.parametrize("value", ["acme", " ACME ", "acme.zendesk.com", "https://acme.zendesk.com/agent/"])
def test_normalize_subdomain(value: str) -> None:
    assert normalize_subdomain(value) == "acme"


def test_every_subscribed_event_type_is_dispatched() -> None:
    trigger = ZendeskTrigger(runtime=None)
    for event_name, zendesk_type in EVENT_TYPE_MAPPING.items():
        assert trigger._dispatch_trigger_events({"type": zendesk_type}) == [event_name]
    assert trigger._dispatch_trigger_events({"type": "zen:event-type:ticket.comment_added"}) == [
        "ticket_comment_created"
    ]
    assert trigger._dispatch_trigger_events({"type": "zen:event-type:ticket.subject_changed"}) == []


def test_dispatch_verifies_signature_and_forwards_payload() -> None:
    payload = _comment_payload("hello")
    body = json.dumps(payload).encode()
    timestamp = "2025-01-15T06:13:26Z"
    signature = base64.b64encode(hmac.new(b"s3cret", timestamp.encode() + body, hashlib.sha256).digest()).decode()
    subscription = Subscription(endpoint="https://dify/hook", properties={"webhook_secret": "s3cret"})
    trigger = ZendeskTrigger(runtime=None)

    dispatch = trigger.dispatch_event(
        subscription,
        _request(
            payload,
            {
                "X-Zendesk-Webhook-Signature": signature,
                "X-Zendesk-Webhook-Signature-Timestamp": timestamp,
            },
        ),
    )
    assert dispatch.events == ["ticket_comment_created"]
    assert dispatch.payload["detail"]["id"] == "342757"

    with pytest.raises(TriggerValidationError):
        trigger.dispatch_event(
            subscription,
            _request(
                payload,
                {"X-Zendesk-Webhook-Signature": "bad", "X-Zendesk-Webhook-Signature-Timestamp": timestamp},
            ),
        )


def test_comment_event_matches_keyword_and_strips_it() -> None:
    event = TicketCommentCreatedEvent(runtime=_event_runtime())
    payload = _comment_payload("#Linear Customer confirmed the fix works")

    variables = event.on_event(
        request=_request(payload), parameters={"body_contains": "#linear, #eng"}, payload=payload
    ).variables

    assert variables["matched_keyword"] == "#linear"
    assert variables["clean_body"] == "Customer confirmed the fix works"
    assert variables["ticket_id"] == "342757"
    assert variables["ticket_url"] == "https://acme.zendesk.com/agent/tickets/342757"
    assert variables["comment"]["body"] == "#Linear Customer confirmed the fix works"


def test_comment_event_filters() -> None:
    event = TicketCommentCreatedEvent(runtime=_event_runtime())
    payload = _comment_payload("no keyword here", is_staff=False)

    with pytest.raises(EventIgnoreError):
        event.on_event(request=_request(payload), parameters={"body_contains": "#linear"}, payload=payload)
    with pytest.raises(EventIgnoreError):
        event.on_event(request=_request(payload), parameters={"author_is_staff": "true"}, payload=payload)
    with pytest.raises(EventIgnoreError):
        event.on_event(request=_request(payload), parameters={"is_public": "true"}, payload=payload)

    variables = event.on_event(
        request=_request(payload), parameters={"body_contains": ",", "strip_keyword": "false"}, payload=payload
    ).variables
    assert variables["matched_keyword"] is None
    assert variables["clean_body"] == "no keyword here"


def test_status_changed_handles_null_previous_value() -> None:
    event = TicketStatusChangedEvent(runtime=_event_runtime())
    payload = {
        "type": "zen:event-type:ticket.status_changed",
        "detail": TICKET,
        "event": {"current": "SOLVED", "previous": None},
    }

    variables = event.on_event(request=_request(payload), parameters={"to_status": "solved"}, payload=payload).variables
    assert variables["current_status"] == "SOLVED"
    assert variables["previous_status"] is None

    with pytest.raises(EventIgnoreError):
        event.on_event(request=_request(payload), parameters={"from_status": "open"}, payload=payload)


CREDENTIALS = {"subdomain": "acme.zendesk.com", "email": "admin@acme.com", "api_token": "tok"}


def _constructor() -> ZendeskSubscriptionConstructor:
    return ZendeskSubscriptionConstructor(runtime=SimpleNamespace(credentials={}, session=None))


def test_create_subscription_fetches_signing_secret() -> None:
    created = _response(201, {"webhook": {"id": "01HWEBHOOK", "status": "active"}})
    secret = _response(200, {"signing_secret": {"algorithm": "SHA256", "secret": "zd-secret"}}, "GET")

    with mock.patch("httpx.post", return_value=created) as post, mock.patch("httpx.get", return_value=secret) as get:
        subscription = _constructor().create_subscription(
            endpoint="https://dify/hook",
            parameters={"events": ["ticket_comment_created", "unknown"]},
            credentials=CREDENTIALS,
            credential_type=CredentialType.API_KEY,
        )

    body = post.call_args.kwargs["json"]["webhook"]
    assert post.call_args.args[0] == "https://acme.zendesk.com/api/v2/webhooks"
    assert body["subscriptions"] == ["zen:event-type:ticket.comment_added"]
    assert "signing_secret" not in body
    assert get.call_args.args[0] == "https://acme.zendesk.com/api/v2/webhooks/01HWEBHOOK/signing_secret"
    assert subscription.properties["external_id"] == "01HWEBHOOK"
    assert subscription.properties["webhook_secret"] == "zd-secret"
    assert subscription.properties["subdomain"] == "acme"


def test_create_subscription_reports_empty_401() -> None:
    with mock.patch("httpx.post", return_value=_response(401)):
        with pytest.raises(SubscriptionError) as exc_info:
            _constructor().create_subscription(
                endpoint="https://dify/hook",
                parameters={"events": ["ticket_created"]},
                credentials=CREDENTIALS,
                credential_type=CredentialType.API_KEY,
            )
    assert "HTTP 401" in str(exc_info.value)
    assert "could not authenticate" in str(exc_info.value)


def test_create_subscription_cleans_up_when_signing_secret_unavailable() -> None:
    created = _response(201, {"webhook": {"id": "01HWEBHOOK"}})
    with (
        mock.patch("httpx.post", return_value=created),
        mock.patch("httpx.get", return_value=_response(403, {"errors": [{"title": "Forbidden"}]}, "GET")),
        mock.patch("httpx.delete") as delete,
    ):
        with pytest.raises(SubscriptionError, match="signing secret"):
            _constructor().create_subscription(
                endpoint="https://dify/hook",
                parameters={"events": ["ticket_created"]},
                credentials=CREDENTIALS,
                credential_type=CredentialType.API_KEY,
            )
    assert delete.call_args.args[0] == "https://acme.zendesk.com/api/v2/webhooks/01HWEBHOOK"


def test_validate_api_key_requires_admin() -> None:
    agent = _response(200, {"user": {"id": 1, "role": "agent"}}, "GET")
    with mock.patch("httpx.get", return_value=agent):
        with pytest.raises(TriggerProviderCredentialValidationError, match="requires an admin"):
            _constructor().validate_api_key(CREDENTIALS)

    admin = _response(200, {"user": {"id": 1, "role": "admin"}}, "GET")
    with mock.patch("httpx.get", return_value=admin) as get:
        _constructor().validate_api_key(CREDENTIALS)
    assert get.call_args.args[0] == "https://acme.zendesk.com/api/v2/users/me.json"

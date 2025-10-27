import hashlib
import hmac
import json

import pytest
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from dify_plugin.entities.trigger import Subscription
from dify_plugin.errors.trigger import SubscriptionError, TriggerValidationError

from notion_trigger.provider.notion_simple import NotionSubscriptionConstructor, NotionTrigger
from notion_trigger.tests.fixtures import COMMENT_CREATED_EVENT, PAGE_CREATED_EVENT


def _make_request(payload, *, token=None, signature_override=None):
    raw_body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    if signature_override is not None:
        headers["X-Notion-Signature"] = signature_override
    elif token is not None and payload.keys() != {"verification_token"}:
        digest = hmac.new(token.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        headers["X-Notion-Signature"] = f"sha256={digest}"

    builder = EnvironBuilder(method="POST", data=raw_body, headers=headers)
    return Request(builder.get_environ())


def _make_subscription(*, verification_token="secret", event_types=None):
    properties = {}
    if verification_token:
        properties["verification_token"] = verification_token
    if event_types is not None:
        properties["event_types"] = event_types
    return Subscription(endpoint="https://example.dify.ai/webhook", properties=properties)


def test_verification_ping_short_circuits():
    trigger = NotionTrigger(runtime=None)
    subscription = _make_subscription(verification_token="secret")
    request = _make_request({"verification_token": "secret"})

    dispatch = trigger._dispatch_event(subscription, request)

    assert dispatch.events == []
    assert dispatch.response.status_code == 200
    assert dispatch.payload == {"verification_token": "secret"}


def test_event_dispatch_returns_normalized_name_and_payload():
    trigger = NotionTrigger(runtime=None)
    subscription = _make_subscription(verification_token="secret")
    request = _make_request(PAGE_CREATED_EVENT, token="secret")

    dispatch = trigger._dispatch_event(subscription, request)

    assert dispatch.events == ["page_created"]
    assert dispatch.payload["type"] == "page.created"
    assert dispatch.response.status_code == 200


def test_event_filter_skips_unselected_types():
    trigger = NotionTrigger(runtime=None)
    subscription = _make_subscription(verification_token="secret", event_types=["comment.created"])
    request = _make_request(PAGE_CREATED_EVENT, token="secret")

    dispatch = trigger._dispatch_event(subscription, request)

    assert dispatch.events == []
    assert dispatch.response.status_code == 200


def test_dispatch_without_verification_token_accepts_payload():
    trigger = NotionTrigger(runtime=None)
    subscription = _make_subscription(verification_token=None)
    request = _make_request(COMMENT_CREATED_EVENT)

    dispatch = trigger._dispatch_event(subscription, request)

    assert dispatch.events == ["comment_created"]


def test_missing_signature_raises_when_token_configured():
    trigger = NotionTrigger(runtime=None)
    subscription = _make_subscription(verification_token="secret")
    request = _make_request(PAGE_CREATED_EVENT)

    with pytest.raises(TriggerValidationError, match="Missing X-Notion-Signature"):
        trigger._dispatch_event(subscription, request)


def test_invalid_signature_rejected():
    trigger = NotionTrigger(runtime=None)
    subscription = _make_subscription(verification_token="secret")
    request = _make_request(
        PAGE_CREATED_EVENT,
        signature_override="sha256=deadbeef",
    )

    with pytest.raises(TriggerValidationError, match="Invalid webhook signature"):
        trigger._dispatch_event(subscription, request)


def test_subscription_constructor_requires_token():
    constructor = NotionSubscriptionConstructor(runtime=None)

    with pytest.raises(SubscriptionError, match="verification_token is required"):
        constructor._create_subscription(
            endpoint="https://example.dify.ai/webhook",
            parameters={},
            credentials={},
            credential_type=None,
        )


def test_subscription_constructor_filters_event_types():
    constructor = NotionSubscriptionConstructor(runtime=None)
    subscription = constructor._create_subscription(
        endpoint="https://example.dify.ai/webhook",
        parameters={
            "verification_token": "secret",
            "event_types": ["page.created", "unknown.event"],
        },
        credentials={},
        credential_type=None,
    )

    assert subscription.properties["verification_token"] == "secret"
    assert subscription.properties["event_types"] == ["page.created"]


def test_subscription_constructor_allows_empty_event_list():
    constructor = NotionSubscriptionConstructor(runtime=None)
    subscription = constructor._create_subscription(
        endpoint="https://example.dify.ai/webhook",
        parameters={
            "verification_token": "secret",
            "event_types": [],
        },
        credentials={},
        credential_type=None,
    )

    assert subscription.properties["event_types"] is None

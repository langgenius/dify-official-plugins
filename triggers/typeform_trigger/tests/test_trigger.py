import base64
import copy
import hashlib
import hmac
import json

import pytest
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from dify_plugin.entities.trigger import Subscription
from dify_plugin.errors.trigger import SubscriptionError, TriggerDispatchError, TriggerValidationError

from typeform_trigger.provider.typeform_simple import TypeformSubscriptionConstructor, TypeformTrigger
from typeform_trigger.tests.fixtures import FORM_RESPONSE_PAYLOAD


def _make_request(
    payload: dict,
    *,
    secret: str | None = None,
    include_header: bool = True,
    signature_override: str | None = None,
) -> Request:
    raw_body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}

    if signature_override is not None:
        headers["Typeform-Signature"] = signature_override
    elif secret and include_header:
        digest = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
        headers["Typeform-Signature"] = "sha256=" + base64.b64encode(digest).decode("ascii")

    builder = EnvironBuilder(method="POST", data=raw_body, headers=headers)
    return Request(builder.get_environ())


def _make_subscription(*, form_id: str | None = None, secret: str | None = None) -> Subscription:
    properties = {}
    if form_id:
        properties["form_id"] = form_id
    if secret:
        properties["webhook_secret"] = secret
    return Subscription(endpoint="https://example.dify.ai/webhook", properties=properties)


def test_dispatch_returns_event():
    trigger = TypeformTrigger(runtime=None)
    subscription = _make_subscription(form_id="lT4Z3j", secret="secret")
    request = _make_request(FORM_RESPONSE_PAYLOAD, secret="secret")

    dispatch = trigger._dispatch_event(subscription, request)

    assert dispatch.events == ["form_response_received"]
    assert dispatch.payload["form_response"]["token"] == "a3a12ec67a1365927098a606107fac15"


def test_form_id_filter_ignored_when_mismatch():
    trigger = TypeformTrigger(runtime=None)
    subscription = _make_subscription(form_id="other-form")
    request = _make_request(FORM_RESPONSE_PAYLOAD)

    dispatch = trigger._dispatch_event(subscription, request)

    assert dispatch.events == []


def test_missing_signature_raises_when_secret_configured():
    trigger = TypeformTrigger(runtime=None)
    subscription = _make_subscription(secret="secret")
    request = _make_request(FORM_RESPONSE_PAYLOAD, secret=None, include_header=False)

    with pytest.raises(TriggerValidationError, match="Missing Typeform-Signature"):
        trigger._dispatch_event(subscription, request)


def test_invalid_signature_raises():
    trigger = TypeformTrigger(runtime=None)
    subscription = _make_subscription(secret="secret")
    request = _make_request(
        FORM_RESPONSE_PAYLOAD,
        signature_override="sha256=invalid",
    )

    with pytest.raises(TriggerValidationError, match="Invalid webhook signature"):
        trigger._dispatch_event(subscription, request)


def test_dispatch_allows_requests_without_secret():
    trigger = TypeformTrigger(runtime=None)
    subscription = _make_subscription()
    request = _make_request(FORM_RESPONSE_PAYLOAD)

    dispatch = trigger._dispatch_event(subscription, request)

    assert dispatch.events == ["form_response_received"]


def test_unknown_event_type_rejected():
    trigger = TypeformTrigger(runtime=None)
    subscription = _make_subscription(secret="secret")
    payload = copy.deepcopy(FORM_RESPONSE_PAYLOAD)
    payload["event_type"] = "form_deleted"
    request = _make_request(payload, secret="secret")

    with pytest.raises(TriggerDispatchError, match="Unsupported Typeform event_type"):
        trigger._dispatch_event(subscription, request)


def test_subscription_constructor_stores_properties():
    constructor = TypeformSubscriptionConstructor(runtime=None)
    subscription = constructor._create_subscription(
        endpoint="https://example.dify.ai/webhook",
        parameters={"form_id": "lT4Z3j", "webhook_secret": "secret"},
        credentials={},
        credential_type=None,
    )

    assert subscription.properties["form_id"] == "lT4Z3j"
    assert subscription.properties["webhook_secret"] == "secret"


def test_subscription_constructor_validates_types():
    constructor = TypeformSubscriptionConstructor(runtime=None)

    with pytest.raises(SubscriptionError, match="form_id must be a string"):
        constructor._create_subscription(
            endpoint="https://example.dify.ai/webhook",
            parameters={"form_id": 123},
            credentials={},
            credential_type=None,
        )

    with pytest.raises(SubscriptionError, match="webhook_secret must be a string"):
        constructor._create_subscription(
            endpoint="https://example.dify.ai/webhook",
            parameters={"webhook_secret": 999},
            credentials={},
            credential_type=None,
        )

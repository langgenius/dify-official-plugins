import copy

import pytest

from dify_plugin.errors.trigger import EventIgnoreError

from typeform_trigger.events.form.form_response_received import FormResponseReceivedEvent
from typeform_trigger.tests.fixtures import FORM_RESPONSE_PAYLOAD


class _MockRequest:
    def __init__(self, payload):
        self._payload = payload

    def get_json(self):
        return self._payload


def _make_request(payload):
    return _MockRequest(copy.deepcopy(payload))


def test_event_passes_payload_through():
    event = FormResponseReceivedEvent(runtime=None)
    result = event._on_event(_make_request(FORM_RESPONSE_PAYLOAD), parameters={}, payload=None)

    assert result.variables["event_type"] == "form_response"
    assert result.variables["form_response"]["form_id"] == "lT4Z3j"


def test_hidden_field_filter_match():
    event = FormResponseReceivedEvent(runtime=None)
    params = {"hidden_field_filter": "user_id=abc123456"}

    result = event._on_event(_make_request(FORM_RESPONSE_PAYLOAD), parameters=params)
    assert result.variables["form_response"]["hidden"]["user_id"] == "abc123456"


def test_hidden_field_filter_no_match():
    event = FormResponseReceivedEvent(runtime=None)
    params = {"hidden_field_filter": "user_id=zzz"}

    with pytest.raises(EventIgnoreError):
        event._on_event(_make_request(FORM_RESPONSE_PAYLOAD), parameters=params)


def test_variable_filter_match():
    event = FormResponseReceivedEvent(runtime=None)
    params = {"variable_filter": "score=4"}

    result = event._on_event(_make_request(FORM_RESPONSE_PAYLOAD), parameters=params)
    variables = result.variables["form_response"]["variables"]
    assert any(item.get("key") == "score" for item in variables)


def test_variable_filter_no_match():
    event = FormResponseReceivedEvent(runtime=None)
    params = {"variable_filter": "score=10"}

    with pytest.raises(EventIgnoreError):
        event._on_event(_make_request(FORM_RESPONSE_PAYLOAD), parameters=params)


def test_invalid_filter_format_raises():
    event = FormResponseReceivedEvent(runtime=None)
    params = {"variable_filter": "score"}

    with pytest.raises(ValueError, match="key=value"):
        event._on_event(_make_request(FORM_RESPONSE_PAYLOAD), parameters=params)

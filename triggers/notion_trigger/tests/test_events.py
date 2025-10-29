import copy

import pytest

from dify_plugin.errors.trigger import EventIgnoreError

from notion_trigger.events.page.page_created import PageCreatedEvent
from notion_trigger.tests.fixtures import PAGE_CREATED_EVENT


class _MockRequest:
    def __init__(self, payload):
        self._payload = payload

    def get_json(self):
        return self._payload


def _make_request(payload):
    return _MockRequest(copy.deepcopy(payload))


def test_page_created_passes_through():
    event = PageCreatedEvent(runtime=None)
    result = event._on_event(_make_request(PAGE_CREATED_EVENT), parameters={})

    assert result.variables["id"] == PAGE_CREATED_EVENT["id"]
    assert result.variables["type"] == "page.created"


def test_workspace_filter_allows_matching_workspace():
    event = PageCreatedEvent(runtime=None)
    params = {"workspace_filter": "other, 13950b26-c203-4f3b-b97d-93ec06319565"}

    result = event._on_event(_make_request(PAGE_CREATED_EVENT), params)
    assert result.variables["workspace_id"] == "13950b26-c203-4f3b-b97d-93ec06319565"


def test_workspace_filter_rejects_non_matching_workspace():
    event = PageCreatedEvent(runtime=None)
    params = {"workspace_filter": "workspace-a,workspace-b"}

    with pytest.raises(EventIgnoreError):
        event._on_event(_make_request(PAGE_CREATED_EVENT), params)


def test_type_mismatch_is_ignored():
    event = PageCreatedEvent(runtime=None)
    payload = copy.deepcopy(PAGE_CREATED_EVENT)
    payload["type"] = "page.deleted"

    with pytest.raises(EventIgnoreError):
        event._on_event(_make_request(payload), parameters={})


def test_empty_payload_raises_value_error():
    event = PageCreatedEvent(runtime=None)

    with pytest.raises(ValueError, match="No payload received"):
        event._on_event(_make_request(None), parameters={})

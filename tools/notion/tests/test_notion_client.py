import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import notion_client as module
from tools.notion_client import NotionClient, extract_notion_id

DATABASE_ID = "3ed2f3c8c2528000b0dfd5f7c47e7d6d"
DATA_SOURCE_ID = "1b2c3d4e0000400080000000000000ff"


def _http_error(status_code):
    response = requests.Response()
    response.status_code = status_code
    return requests.HTTPError(f"HTTP {status_code}", response=response)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (DATABASE_ID, DATABASE_ID),
        (" 3ed2f3c8-c252-8000-b0df-d5f7c47e7d6d ", "3ed2f3c8-c252-8000-b0df-d5f7c47e7d6d"),
        (f"https://www.notion.so/team/Tasks-{DATABASE_ID}?v={DATA_SOURCE_ID}", DATABASE_ID),
        (f"https://www.notion.so/{DATABASE_ID}#section", DATABASE_ID),
        ("db1", "db1"),
    ],
)
def test_extract_notion_id(value, expected):
    assert extract_notion_id(value) == expected


class _Responses:
    """Stands in for NotionClient._make_request, answering by endpoint."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, method, endpoint, **kwargs):
        self.calls.append(endpoint)
        response = self.responses[endpoint]
        if isinstance(response, Exception):
            raise response
        return response


def _client(monkeypatch, responses):
    client = NotionClient("secret-token")
    fake = _Responses(responses)
    monkeypatch.setattr(client, "_make_request", fake)
    return client, fake


def test_resolve_data_source_uses_the_first_data_source_of_a_database(monkeypatch):
    client, fake = _client(monkeypatch, {
        f"/databases/{DATABASE_ID}": {"data_sources": [{"id": DATA_SOURCE_ID}, {"id": "other"}]},
        f"/data_sources/{DATA_SOURCE_ID}": {"id": DATA_SOURCE_ID, "properties": {}},
    })

    assert client.resolve_data_source(f"https://www.notion.so/Tasks-{DATABASE_ID}")["id"] == DATA_SOURCE_ID
    assert fake.calls == [f"/databases/{DATABASE_ID}", f"/data_sources/{DATA_SOURCE_ID}"]


@pytest.mark.parametrize("status_code", [400, 404])
def test_resolve_data_source_accepts_a_data_source_id(monkeypatch, status_code):
    client, _ = _client(monkeypatch, {
        f"/databases/{DATA_SOURCE_ID}": _http_error(status_code),
        f"/data_sources/{DATA_SOURCE_ID}": {"id": DATA_SOURCE_ID, "properties": {}},
    })

    assert client.resolve_data_source(DATA_SOURCE_ID)["id"] == DATA_SOURCE_ID


def test_resolve_data_source_reports_the_database_error_when_neither_matches(monkeypatch):
    database_error = _http_error(404)
    client, _ = _client(monkeypatch, {
        f"/databases/{DATABASE_ID}": database_error,
        f"/data_sources/{DATABASE_ID}": _http_error(400),
    })

    with pytest.raises(requests.HTTPError) as raised:
        client.resolve_data_source(DATABASE_ID)
    assert raised.value is database_error


def test_resolve_data_source_does_not_fall_back_on_other_errors(monkeypatch):
    client, fake = _client(monkeypatch, {f"/databases/{DATABASE_ID}": _http_error(500)})

    with pytest.raises(requests.HTTPError):
        client.resolve_data_source(DATABASE_ID)
    assert fake.calls == [f"/databases/{DATABASE_ID}"]


class _FlakyRequest:
    def __init__(self, errors):
        self.errors = list(errors)
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.errors:
            raise self.errors.pop(0)
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"id": "page"}'
        return response


def _patch_requests(monkeypatch, errors):
    flaky = _FlakyRequest(errors)
    monkeypatch.setattr(module.requests, "request", flaky)
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    return flaky


def test_network_errors_are_retried_by_default(monkeypatch):
    flaky = _patch_requests(monkeypatch, [requests.ConnectionError("reset")])

    assert NotionClient("t")._make_request("get", "/pages/x") == {"id": "page"}
    assert len(flaky.calls) == 2
    assert flaky.calls[0]["timeout"] is None


def test_non_idempotent_requests_are_not_retried_after_sending(monkeypatch):
    flaky = _patch_requests(monkeypatch, [requests.ConnectionError("reset")])

    with pytest.raises(requests.ConnectionError):
        NotionClient("t").create_page({"data_source_id": "ds"}, {}, retry_network_errors=False, timeout=60)
    assert len(flaky.calls) == 1
    assert flaky.calls[0]["timeout"] == 60


def test_non_idempotent_requests_still_retry_connect_timeouts(monkeypatch):
    flaky = _patch_requests(monkeypatch, [requests.ConnectTimeout("connect timed out")])

    assert NotionClient("t").append_block_children("page", [], retry_network_errors=False) == {"id": "page"}
    assert len(flaky.calls) == 2

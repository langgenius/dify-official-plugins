import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import update_database_record as module
from tools.update_database_record import (
    InvalidPropertyValueError,
    UpdateDatabaseRecordTool,
    _build_match_filter,
    _build_properties_payload,
    _to_property_value,
)

DATABASE_ID = "db1"
USER_ID = "1b2c3d4e-0000-4000-8000-000000000001"
PAGE_REF_ID = "1b2c3d4e00004000800000000000000a"

SCHEMA = {
    "No": {"type": "number"},
    "Name": {"type": "title"},
    "Memo": {"type": "rich_text"},
    "Status": {"type": "status"},
    "Stage": {"type": "select"},
    "Tags": {"type": "multi_select"},
    "Due": {"type": "date"},
    "Done": {"type": "checkbox"},
    "Link": {"type": "url"},
    "Owner": {"type": "people"},
    "Related": {"type": "relation"},
    "Docs": {"type": "files"},
    "Total": {"type": "formula"},
    "Ticket": {"type": "unique_id"},
}
TYPES = {name: data["type"] for name, data in SCHEMA.items()}


class _MessageToolMixin:
    def create_text_message(self, value):
        return {"type": "text", "value": value}

    def create_json_message(self, value):
        return {"type": "json", "value": value}


def _http_error(status_code):
    response = requests.Response()
    response.status_code = status_code
    return requests.HTTPError(f"HTTP {status_code}", response=response)


class _FakeClient:
    def __init__(self, result_pages=None, pages=None, fail_on=None, lookup_error=None):
        # result_pages: list of pages of matching IDs, returned one per query call
        self.result_pages = result_pages if result_pages is not None else [[]]
        self.pages = pages or {}
        self.fail_on = fail_on or {}
        self.lookup_error = lookup_error
        self.queries = []
        self.updates = []

    def retrieve_page(self, page_id):
        if self.lookup_error:
            raise self.lookup_error
        return self.pages[page_id]

    def get_default_data_source_id(self, database_id):
        if self.lookup_error:
            raise self.lookup_error
        return "ds-1"

    def retrieve_data_source(self, data_source_id):
        return {"properties": SCHEMA}

    def query_data_source(self, data_source_id, filter_obj=None, page_size=10, start_cursor=None):
        index = int(start_cursor or 0)
        self.queries.append({"filter": filter_obj, "page_size": page_size, "start_cursor": start_cursor})
        has_more = index + 1 < len(self.result_pages)
        return {
            "results": [{"id": page_id} for page_id in self.result_pages[index][:page_size]],
            "has_more": has_more,
            "next_cursor": str(index + 1) if has_more else None,
        }

    def update_page(self, page_id, properties, archived=False):
        if page_id in self.fail_on:
            raise self.fail_on[page_id]
        self.updates.append((page_id, properties))
        return {"id": page_id}

    def format_page_url(self, page_id):
        return f"https://www.notion.so/{page_id}"


def _run(client, monkeypatch, **params):
    monkeypatch.setattr(module, "NotionClient", lambda token: client)
    tool = object.__new__(UpdateDatabaseRecordTool)
    tool.runtime = SimpleNamespace(credentials={"integration_token": "secret-token"})
    for name in ("create_text_message", "create_json_message"):
        setattr(tool, name, getattr(_MessageToolMixin, name).__get__(tool, UpdateDatabaseRecordTool))
    messages = list(tool._invoke(params))
    assert messages[-1]["type"] == "json"
    return messages[-1]["value"]


def _match(**params):
    return {"database_id": DATABASE_ID, "match_property": "No", "match_value": "2", **params}


# --- value conversion -----------------------------------------------------------------


def test_converts_simple_values_by_property_type():
    payload = _build_properties_payload(
        {
            "Name": "D", "No": "3", "Status": "Done", "Stage": None, "Tags": ["a", None, "b"],
            "Due": "2026-10-01", "Done": "Yes", "Memo": "", "Link": "",
            "Owner": [USER_ID], "Related": f'["{PAGE_REF_ID}"]',
            "Docs": ["https://example.com/files/report.pdf?sig=abc"],
        },
        TYPES,
    )

    assert payload == {
        "Name": {"title": [{"type": "text", "text": {"content": "D"}}]},
        "No": {"number": 3},
        "Status": {"status": {"name": "Done"}},
        "Stage": {"select": None},
        "Tags": {"multi_select": [{"name": "a"}, {"name": "b"}]},
        "Due": {"date": {"start": "2026-10-01"}},
        "Done": {"checkbox": True},
        "Memo": {"rich_text": []},
        "Link": {"url": None},
        "Owner": {"people": [{"id": USER_ID}]},
        "Related": {"relation": [{"id": PAGE_REF_ID}]},
        "Docs": {"files": [{"name": "report.pdf", "type": "external",
                            "external": {"url": "https://example.com/files/report.pdf?sig=abc"}}]},
    }


def test_comma_separated_string_is_split_for_multi_select():
    assert _to_property_value("Tags", "multi_select", "a, b") == {"multi_select": [{"name": "a"}, {"name": "b"}]}


def test_date_accepts_datetime_and_range():
    assert _to_property_value("Due", "date", "2026-10-01T09:00:00+09:00") == {"date": {"start": "2026-10-01T09:00:00+09:00"}}
    value = {"start": "2026-10-01", "end": "2026-10-03"}
    assert _to_property_value("Due", "date", {"date": value}) == {"date": value}


def test_long_text_is_split_into_notion_sized_chunks():
    value = _to_property_value("Memo", "rich_text", "x" * 4500)
    assert [len(item["text"]["content"]) for item in value["rich_text"]] == [2000, 2000, 500]


def test_chunks_count_utf16_code_units():
    # Each emoji is 2 UTF-16 code units, so only 1000 fit in one Notion text object
    value = _to_property_value("Memo", "rich_text", "😀" * 1500)
    assert [len(item["text"]["content"]) for item in value["rich_text"]] == [1000, 500]


def test_raw_notion_format_is_passed_through():
    raw = {"rich_text": [{"type": "text", "text": {"content": "hi"}, "annotations": {"bold": True}}]}
    assert _to_property_value("Memo", "rich_text", raw) is raw


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"Total": 1}, "read-only"),
        ({"Total": {"formula": {"number": 1}}}, "read-only"),
        ({"Missing": 1}, "does not exist"),
        ({"No": "abc"}, "numeric value"),
        ({"No": "inf"}, "finite number"),
        ({"No": True}, "numeric value"),
        ({"Done": "はい"}, "true or false"),
        ({"Done": None}, "true or false"),
        ({"Name": ""}, "cannot be cleared"),
        ({"Name": ["a"]}, "text value"),
        ({"Stage": ["a"]}, "single text value"),
        ({"Due": "2026/10/01"}, "ISO 8601"),
        ({"Due": {"end": "2026-10-01"}}, "'start'"),
        ({"Owner": ["taro@example.com"]}, "user IDs"),
        ({"Related": ["not-an-id"]}, "page IDs"),
        ({"Memo": "x" * 200_001}, "too long"),
    ],
)
def test_rejects_invalid_values(values, message):
    with pytest.raises(InvalidPropertyValueError, match=message):
        _build_properties_payload(values, TYPES)


# --- match filter -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("prop", "value", "expected"),
    [
        ("No", "2", {"property": "No", "number": {"equals": 2}}),
        ("Ticket", "TASK-2", {"property": "Ticket", "unique_id": {"equals": 2}}),
        ("Ticket", "7", {"property": "Ticket", "unique_id": {"equals": 7}}),
        ("Done", "True", {"property": "Done", "checkbox": {"equals": True}}),
        ("Name", "A", {"property": "Name", "title": {"equals": "A"}}),
        ("Due", "2026-10-01", {"property": "Due", "date": {"equals": "2026-10-01"}}),
    ],
)
def test_builds_exact_match_filter(prop, value, expected):
    assert _build_match_filter(prop, value, SCHEMA[prop]) == expected


@pytest.mark.parametrize(
    ("prop", "value", "message"),
    [
        ("Tags", "a", "cannot be used as match_property"),
        ("Owner", USER_ID, "cannot be used as match_property"),
        ("Total", "2", "cannot be used as match_property"),
        ("Ticket", "TASK-X", "ID number"),
        ("No", "two", "numeric value"),
        ("Done", "maybe", "true or false"),
    ],
)
def test_rejects_invalid_match(prop, value, message):
    with pytest.raises(InvalidPropertyValueError, match=message):
        _build_match_filter(prop, value, SCHEMA[prop])


# --- tool flow --------------------------------------------------------------------------


def test_updates_single_record_found_by_match_condition(monkeypatch):
    client = _FakeClient(result_pages=[["page-2"]])

    result = _run(client, monkeypatch, properties=json.dumps({"Name": "D"}), **_match())

    assert client.queries[0]["filter"] == {"property": "No", "number": {"equals": 2}}
    assert client.updates == [("page-2", {"Name": {"title": [{"type": "text", "text": {"content": "D"}}]}})]
    assert result["status"] == "updated"
    assert result["updated_count"] == 1
    assert result["updated_records"] == [{"id": "page-2", "url": "https://www.notion.so/page-2"}]


def test_refuses_ambiguous_match_and_returns_candidates(monkeypatch):
    client = _FakeClient(result_pages=[["page-1", "page-2", "page-3"]])

    result = _run(client, monkeypatch, properties=json.dumps({"Done": True}), **_match())

    assert result["status"] == "ambiguous"
    assert [c["id"] for c in result["candidates"]] == ["page-1", "page-2"]
    assert client.queries[0]["page_size"] == 2
    assert client.updates == []


def test_update_all_matches_paginates_and_updates_every_record(monkeypatch):
    client = _FakeClient(result_pages=[["page-1", "page-2"], ["page-3"]])

    result = _run(client, monkeypatch, properties=json.dumps({"Done": True}), update_all_matches=True, **_match())

    assert result["status"] == "updated"
    assert [page_id for page_id, _ in client.updates] == ["page-1", "page-2", "page-3"]
    assert [q["start_cursor"] for q in client.queries] == [None, "1"]


def test_update_all_matches_refuses_more_than_max_updates(monkeypatch):
    client = _FakeClient(result_pages=[["page-1", "page-2"], ["page-3", "page-4"]])

    result = _run(
        client, monkeypatch, properties=json.dumps({"Done": True}), update_all_matches=True, max_updates=2, **_match()
    )

    assert result["status"] == "too_many_matches"
    assert [c["id"] for c in result["candidates"]] == ["page-1", "page-2", "page-3"]
    assert client.updates == []


def test_reports_progress_when_an_update_fails_midway(monkeypatch):
    client = _FakeClient(
        result_pages=[["page-1", "page-2", "page-3"]],
        fail_on={"page-2": requests.ConnectionError("connection reset")},
    )

    result = _run(client, monkeypatch, properties=json.dumps({"Done": True}), update_all_matches=True, **_match())

    assert result["status"] == "partially_updated"
    assert result["updated_records"] == [{"id": "page-1", "url": "https://www.notion.so/page-1"}]
    assert result["failed_record"]["id"] == "page-2"
    assert result["pending_ids"] == ["page-3"]


def test_first_update_failure_is_an_error(monkeypatch):
    client = _FakeClient(result_pages=[["page-1"]], fail_on={"page-1": _http_error(400)})

    result = _run(client, monkeypatch, properties=json.dumps({"Done": True}), **_match())

    assert result["status"] == "error"
    assert result["updated_count"] == 0


def test_reports_when_no_record_matches(monkeypatch):
    client = _FakeClient(result_pages=[[]])

    result = _run(client, monkeypatch, properties=json.dumps({"Name": "D"}), **_match(match_value="9"))

    assert result == {"status": "not_found", "message": "No record found where No = 9.", "matched_count": 0}


def test_invalid_values_are_rejected_before_querying(monkeypatch):
    client = _FakeClient(result_pages=[["page-2"]])

    result = _run(client, monkeypatch, properties=json.dumps({"Done": "maybe"}), **_match())

    assert result["status"] == "invalid_input"
    assert client.queries == []


def test_unknown_match_property(monkeypatch):
    result = _run(_FakeClient(), monkeypatch, properties=json.dumps({"Name": "D"}), **_match(match_property="Nope"))

    assert result["status"] == "invalid_input"
    assert "Match property 'Nope' does not exist" in result["message"]


def test_database_not_accessible(monkeypatch):
    client = _FakeClient(lookup_error=_http_error(404))

    result = _run(client, monkeypatch, properties=json.dumps({"Name": "D"}), **_match())

    assert result["status"] == "not_accessible"
    assert result["message"].startswith(f"Database {DATABASE_ID} was not found or is not shared with this integration.")


def test_lookup_http_error(monkeypatch):
    client = _FakeClient(lookup_error=_http_error(500))

    result = _run(client, monkeypatch, properties=json.dumps({"Name": "D"}), **_match())

    assert result["status"] == "error"


def _db_page(page_id, database_id=DATABASE_ID, parent_type="data_source_id"):
    return {
        "id": page_id,
        "parent": {"type": parent_type, "data_source_id": "ds-1", "database_id": database_id},
        "properties": {"Memo": {"type": "rich_text"}},
    }


def test_updates_by_page_id_using_page_property_types(monkeypatch):
    client = _FakeClient(pages={"page-2": _db_page("page-2")})

    result = _run(client, monkeypatch, page_id="page-2", properties=json.dumps({"Memo": "updated"}))

    assert result["status"] == "updated"
    assert client.updates == [("page-2", {"Memo": {"rich_text": [{"type": "text", "text": {"content": "updated"}}]}})]


def test_page_id_must_belong_to_given_database(monkeypatch):
    client = _FakeClient(pages={"page-2": _db_page("page-2", database_id="other-db")})

    result = _run(client, monkeypatch, page_id="page-2", database_id=DATABASE_ID, properties=json.dumps({"Memo": "x"}))

    assert result["status"] == "invalid_input"
    assert client.updates == []


def test_page_id_must_be_a_database_record(monkeypatch):
    page = {"id": "page-9", "parent": {"type": "page_id", "page_id": "p"}, "properties": {"title": {"type": "title"}}}
    client = _FakeClient(pages={"page-9": page})

    result = _run(client, monkeypatch, page_id="page-9", properties=json.dumps({"title": "x"}))

    assert result["status"] == "invalid_input"
    assert client.updates == []


@pytest.mark.parametrize(
    ("params", "message"),
    [
        (dict(database_id=DATABASE_ID, properties='{"Name": "D"}'), "Either page_id"),
        (dict(database_id=DATABASE_ID, match_property="No", match_value=None, properties='{"Name": "D"}'), "Either page_id"),
        (dict(page_id="page-2", properties="{not json"), "Invalid JSON"),
        (dict(page_id="page-2", properties="{}"), "non-empty JSON object"),
        (dict(page_id="page-2", properties="[1]"), "non-empty JSON object"),
    ],
)
def test_rejects_invalid_parameters(monkeypatch, params, message):
    result = _run(_FakeClient(), monkeypatch, **params)

    assert result["status"] == "invalid_input"
    assert message in result["message"]

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import update_database_record as module
from tools.notion_properties import InvalidPropertyValueError, build_properties_payload, to_property_value
from tools.update_database_record import UpdateDatabaseRecordTool, _build_match_filter

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
    "Ticket": {"type": "unique_id", "unique_id": {"prefix": "TASK"}},
    "Seq": {"type": "unique_id", "unique_id": {"prefix": None}},
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

    def resolve_data_source(self, database_id):
        if self.lookup_error:
            raise self.lookup_error
        return {"id": "ds-1", "properties": SCHEMA}

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
    payload = build_properties_payload(
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


@pytest.mark.parametrize(
    ("value", "expected"),
    [("9007199254740991", 9007199254740991), (9007199254740991, 9007199254740991), ("-12", -12),
     ("2.50", 2.5), (3.0, 3), ("1e3", 1000)],
)
def test_numbers_are_parsed_without_precision_loss(value, expected):
    result = to_property_value("No", "number", value)["number"]
    assert result == expected and type(result) is type(expected)


def test_comma_separated_string_is_split_for_multi_select():
    assert to_property_value("Tags", "multi_select", "a, b") == {"multi_select": [{"name": "a"}, {"name": "b"}]}


def test_date_accepts_datetime_and_range():
    assert to_property_value("Due", "date", "2026-10-01T09:00:00+09:00") == {"date": {"start": "2026-10-01T09:00:00+09:00"}}
    value = {"start": "2026-10-01", "end": "2026-10-03"}
    assert to_property_value("Due", "date", {"date": value}) == {"date": value}
    assert to_property_value("Due", "date", {"start": " 2026-10-01 ", "end": None, "time_zone": "Asia/Tokyo"}) == {
        "date": {"start": "2026-10-01", "end": None, "time_zone": "Asia/Tokyo"}
    }


def test_long_text_is_split_into_notion_sized_chunks():
    value = to_property_value("Memo", "rich_text", "x" * 4500)
    assert [len(item["text"]["content"]) for item in value["rich_text"]] == [2000, 2000, 500]


def test_chunks_count_utf16_code_units():
    # Each emoji is 2 UTF-16 code units, so only 1000 fit in one Notion text object
    value = to_property_value("Memo", "rich_text", "😀" * 1500)
    assert [len(item["text"]["content"]) for item in value["rich_text"]] == [1000, 500]


def test_raw_notion_format_is_passed_through():
    raw = {"rich_text": [{"type": "text", "text": {"content": "hi"}, "annotations": {"bold": True}}]}
    assert to_property_value("Memo", "rich_text", raw) is raw


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"Total": 1}, "read-only"),
        ({"Total": {"formula": {"number": 1}}}, "read-only"),
        ({"Missing": 1}, "does not exist"),
        ({"No": "abc"}, "numeric value"),
        ({"No": "inf"}, "finite number"),
        ({"No": True}, "numeric value"),
        ({"No": 9007199254740993}, "exactly"),
        ({"No": "9007199254740993"}, "exactly"),
        ({"No": 1e20}, "exactly"),
        ({"No": [1]}, "numeric value"),
        ({"Done": "はい"}, "true or false"),
        ({"Done": None}, "true or false"),
        ({"Name": ""}, "cannot be empty"),
        ({"Name": ["a"]}, "text value"),
        ({"Stage": ["a"]}, "single text value"),
        ({"Due": "2026/10/01"}, "ISO 8601"),
        ({"Due": {"end": "2026-10-01"}}, "'start'"),
        ({"Owner": ["taro@example.com"]}, "user IDs"),
        ({"Related": ["not-an-id"]}, "page IDs"),
        ({"Memo": "x" * 200_001}, "too long"),
        ({"Due": 20261001}, "date string"),
        ({"Due": {"start": 20261001}}, "date string"),
        ({"Due": {"start": {"start": "2026-10-01"}}}, "date string"),
        ({"Due": {"start": "2026-10-01", "end": ""}}, "ISO 8601"),
        ({"Due": {"start": "  "}}, "'start'"),
        ({"Name": {"title": []}}, "cannot be empty"),
        ({"Name": {"title": [{"type": "text", "text": {"content": ""}}]}}, "cannot be empty"),
    ],
)
def test_rejects_invalid_values(values, message):
    with pytest.raises(InvalidPropertyValueError, match=message):
        build_properties_payload(values, TYPES)


# --- match filter -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("prop", "value", "expected"),
    [
        ("No", "2", {"property": "No", "number": {"equals": 2}}),
        ("No", "9007199254740991", {"property": "No", "number": {"equals": 9007199254740991}}),
        ("No", "2.5", {"property": "No", "number": {"equals": 2.5}}),
        ("Ticket", "TASK-2", {"property": "Ticket", "unique_id": {"equals": 2}}),
        ("Ticket", "7", {"property": "Ticket", "unique_id": {"equals": 7}}),
        ("Ticket", "task-7", {"property": "Ticket", "unique_id": {"equals": 7}}),
        ("Seq", "3", {"property": "Seq", "unique_id": {"equals": 3}}),
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
        ("Ticket", "BUG-2", "expects TASK-<number>"),
        ("Seq", "TASK-3", "without a prefix"),
        ("No", "two", "numeric value"),
        ("No", "9007199254740993", "exactly"),
        ("Ticket", "TASK-9007199254740993", "too large"),
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


def test_page_ownership_check_ignores_id_case_and_hyphens(monkeypatch):
    client = _FakeClient(pages={"page-2": _db_page("page-2", database_id="3ed2f3c8-c252-8000-b0df-d5f7c47e7d6d")})

    result = _run(
        client, monkeypatch, page_id="page-2", database_id="3ED2F3C8C2528000B0DFD5F7C47E7D6D",
        properties=json.dumps({"Memo": "x"}),
    )

    assert result["status"] == "updated"


def test_page_ownership_check_accepts_data_source_id_or_url(monkeypatch):
    page = _db_page("page-2", database_id="3ed2f3c8c2528000b0dfd5f7c47e7d6d")
    page["parent"]["data_source_id"] = "1b2c3d4e-0000-4000-8000-0000000000ff"
    client = _FakeClient(pages={"page-2": page})

    by_data_source = _run(
        client, monkeypatch, page_id="page-2", database_id="1B2C3D4E0000400080000000000000FF",
        properties=json.dumps({"Memo": "x"}),
    )
    by_url = _run(
        client, monkeypatch, page_id="page-2",
        database_id="https://www.notion.so/team/Tasks-3ed2f3c8c2528000b0dfd5f7c47e7d6d?v=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        properties=json.dumps({"Memo": "x"}),
    )

    assert by_data_source["status"] == "updated"
    assert by_url["status"] == "updated"


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

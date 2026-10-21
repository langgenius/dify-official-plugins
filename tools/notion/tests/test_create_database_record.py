import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools import create_database_record as module
from tools.create_database_record import WRITE_REQUEST_OPTIONS, CreateDatabaseRecordTool

DATABASE_ID = "db1"
NEW_PAGE_ID = "new-page"
USER_ID = "1b2c3d4e-0000-4000-8000-000000000001"

SCHEMA = {
    "Name": {"type": "title"},
    "No": {"type": "number"},
    "Status": {"type": "status"},
    "Tags": {"type": "multi_select"},
    "Due": {"type": "date"},
    "Done": {"type": "checkbox"},
    "Memo": {"type": "rich_text"},
    "Owner": {"type": "people"},
    "Total": {"type": "formula"},
}


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
    def __init__(self, lookup_error=None, create_error=None, append_error_on_call=None):
        self.lookup_error = lookup_error
        self.create_error = create_error
        self.append_error_on_call = append_error_on_call
        self.created = []
        self.appended = []

    def resolve_data_source(self, database_id):
        if self.lookup_error:
            raise self.lookup_error
        return {"id": "ds-1", "properties": SCHEMA}

    def create_page(self, parent, properties, children=None, **request_options):
        if self.create_error:
            raise self.create_error
        self.created.append({"parent": parent, "properties": properties, "children": children, "options": request_options})
        return {"id": NEW_PAGE_ID, "url": f"https://www.notion.so/{NEW_PAGE_ID}"}

    def append_block_children(self, block_id, children, **request_options):
        if self.append_error_on_call == len(self.appended):
            raise requests.ConnectionError("connection reset")
        self.appended.append((block_id, children))
        return {}

    def format_page_url(self, page_id):
        return f"https://www.notion.so/{page_id}"


def _run(client, monkeypatch, credentials=None, **params):
    monkeypatch.setattr(module, "NotionClient", lambda token: client)
    tool = object.__new__(CreateDatabaseRecordTool)
    tool.runtime = SimpleNamespace(credentials={"integration_token": "secret-token"} if credentials is None else credentials)
    for name in ("create_text_message", "create_json_message"):
        setattr(tool, name, getattr(_MessageToolMixin, name).__get__(tool, CreateDatabaseRecordTool))
    messages = list(tool._invoke(params))
    assert messages[-1]["type"] == "json"
    return messages[-1]["value"]


def _texts(block):
    return [item["text"]["content"] for item in block["paragraph"]["rich_text"]]


def _lines(count, width=0):
    return "\n".join(f"line {i}".ljust(width, "x") for i in range(count))


def test_creates_record_with_converted_property_values(monkeypatch):
    client = _FakeClient()

    result = _run(
        client, monkeypatch, database_id=DATABASE_ID,
        properties=json.dumps({
            "Name": "Task A", "No": "3", "Status": "Todo", "Tags": ["a", "b"], "Due": "2026-10-01", "Done": "yes",
            "Owner": [USER_ID],
        }),
    )

    created = client.created[0]
    assert created["parent"] == {"type": "data_source_id", "data_source_id": "ds-1"}
    assert created["properties"] == {
        "Name": {"title": [{"type": "text", "text": {"content": "Task A"}}]},
        "No": {"number": 3},
        "Status": {"status": {"name": "Todo"}},
        "Tags": {"multi_select": [{"name": "a"}, {"name": "b"}]},
        "Due": {"date": {"start": "2026-10-01"}},
        "Done": {"checkbox": True},
        "Owner": {"people": [{"id": USER_ID}]},
    }
    assert not created["children"]
    assert created["options"] == WRITE_REQUEST_OPTIONS
    assert result["status"] == "created"
    assert result["record"] == {"id": NEW_PAGE_ID, "url": f"https://www.notion.so/{NEW_PAGE_ID}"}
    assert result["set_properties"] == ["Name", "No", "Status", "Tags", "Due", "Done", "Owner"]


def test_raw_notion_format_is_passed_through(monkeypatch):
    client = _FakeClient()
    raw = {"rich_text": [{"type": "text", "text": {"content": "hi"}, "annotations": {"bold": True}}]}

    _run(client, monkeypatch, database_id=DATABASE_ID, properties=json.dumps({"Memo": raw}))

    assert client.created[0]["properties"] == {"Memo": raw}


def test_empty_values_are_left_unset(monkeypatch):
    client = _FakeClient()

    result = _run(
        client, monkeypatch, database_id=DATABASE_ID,
        properties=json.dumps({"Name": "", "Done": None, "Memo": "  ", "No": 0}),
    )

    assert client.created[0]["properties"] == {"No": {"number": 0}}
    assert result["status"] == "created"


def test_refuses_to_create_a_blank_record(monkeypatch):
    client = _FakeClient()

    result = _run(client, monkeypatch, database_id=DATABASE_ID, properties=json.dumps({"Name": "", "Memo": " "}))

    assert result["status"] == "invalid_input"
    assert "nothing to create" in result["message"]
    assert client.created == []


def test_content_alone_is_enough_to_create(monkeypatch):
    client = _FakeClient()

    result = _run(client, monkeypatch, database_id=DATABASE_ID, properties='{"Name": null}', content="note")

    assert result["status"] == "created"
    assert client.created[0]["properties"] == {}


def test_content_becomes_paragraphs(monkeypatch):
    client = _FakeClient()

    _run(client, monkeypatch, database_id=DATABASE_ID, properties='{"Name": "A"}', content="first\r\n\r\nsecond\x0cpart\n")

    children = client.created[0]["children"]
    assert [_texts(block) for block in children] == [["first"], [], ["second\x0cpart"]]
    assert client.appended == []


def test_whitespace_only_content_adds_nothing(monkeypatch):
    client = _FakeClient()

    _run(client, monkeypatch, database_id=DATABASE_ID, properties='{"Name": "A"}', content=" \n\t\n")

    assert not client.created[0]["children"]


def test_long_content_is_appended_in_batches(monkeypatch):
    client = _FakeClient()

    result = _run(client, monkeypatch, database_id=DATABASE_ID, properties='{"Name": "A"}', content=_lines(250))

    assert len(client.created[0]["children"]) == 100
    assert [(block_id, len(children)) for block_id, children in client.appended] == [(NEW_PAGE_ID, 100), (NEW_PAGE_ID, 50)]
    assert _texts(client.appended[-1][1][-1]) == ["line 249"]
    assert result["status"] == "created"


def test_content_batches_are_limited_by_size(monkeypatch):
    client = _FakeClient()
    # Each line is about 12 KB once serialised (Japanese is \\u-escaped), so ~33 fit in one request
    content = "\n".join("あ" * 2000 for _ in range(50))

    result = _run(client, monkeypatch, database_id=DATABASE_ID, properties='{"Name": "A"}', content=content)

    sizes = [len(client.created[0]["children"])] + [len(children) for _, children in client.appended]
    assert sum(sizes) == 50 and len(sizes) == 2
    for batch in [client.created[0]["children"]] + [children for _, children in client.appended]:
        assert len(json.dumps(batch)) <= module.MAX_CONTENT_BYTES_PER_REQUEST
    assert result["status"] == "created"


def test_large_properties_push_content_to_append_requests(monkeypatch):
    client = _FakeClient()
    memo = "あ" * 70_000  # ~420 KB once serialised, leaving no room for content in the create request

    result = _run(
        client, monkeypatch, database_id=DATABASE_ID, properties=json.dumps({"Name": "A", "Memo": memo}), content="body",
    )

    assert not client.created[0]["children"]
    assert [_texts(children[0]) for _, children in client.appended] == [["body"]]
    assert result["status"] == "created"


def test_too_long_content_line_is_rejected(monkeypatch):
    client = _FakeClient()

    result = _run(client, monkeypatch, database_id=DATABASE_ID, properties='{"Name": "A"}', content="ok\n" + "x" * 200_001)

    assert result["status"] == "invalid_input"
    assert result["message"].startswith("Content line 2 is too long")
    assert client.created == []


@pytest.mark.parametrize(("fail_on_call", "added"), [(0, 100), (1, 200)])
def test_reports_partial_creation_when_appending_content_fails(monkeypatch, fail_on_call, added):
    client = _FakeClient(append_error_on_call=fail_on_call)

    result = _run(client, monkeypatch, database_id=DATABASE_ID, properties='{"Name": "A"}', content=_lines(250))

    assert result["status"] == "partially_created"
    assert result["record"]["id"] == NEW_PAGE_ID
    assert f"after {added} of 250 lines" in result["message"]


@pytest.mark.parametrize(
    ("properties", "message"),
    [
        ('{"Missing": 1}', "does not exist"),
        ('{"Total": 1}', "read-only"),
        ('{"No": "abc"}', "numeric value"),
        ('{"Done": "maybe"}', "true or false"),
        ('{"Owner": ["taro@example.com"]}', "user IDs"),
        ('{"Name": {"title": []}}', "cannot be empty"),
    ],
)
def test_invalid_values_are_rejected_before_creating(monkeypatch, properties, message):
    client = _FakeClient()

    result = _run(client, monkeypatch, database_id=DATABASE_ID, properties=properties)

    assert result["status"] == "invalid_input"
    assert message in result["message"]
    assert client.created == []


@pytest.mark.parametrize(
    ("params", "message"),
    [
        (dict(properties='{"Name": "A"}'), "database_id is required"),
        (dict(database_id=DATABASE_ID, properties="{not json"), "Invalid JSON"),
        (dict(database_id=DATABASE_ID, properties="{}"), "non-empty JSON object"),
        (dict(database_id=DATABASE_ID, properties="[1]"), "non-empty JSON object"),
    ],
)
def test_rejects_invalid_parameters(monkeypatch, params, message):
    result = _run(_FakeClient(), monkeypatch, **params)

    assert result["status"] == "invalid_input"
    assert message in result["message"]


def test_missing_integration_token(monkeypatch):
    result = _run(_FakeClient(), monkeypatch, credentials={}, database_id=DATABASE_ID, properties='{"Name": "A"}')

    assert result["status"] == "error"
    assert "Integration Token is required" in result["message"]


def test_database_not_accessible(monkeypatch):
    result = _run(_FakeClient(lookup_error=_http_error(404)), monkeypatch, database_id=DATABASE_ID, properties='{"Name": "A"}')

    assert result["status"] == "not_accessible"
    assert result["message"].startswith(f"Database {DATABASE_ID} was not found or is not shared with this integration.")


@pytest.mark.parametrize("error", [_http_error(500), ValueError("No data sources found for database db1")])
def test_lookup_errors(monkeypatch, error):
    result = _run(_FakeClient(lookup_error=error), monkeypatch, database_id=DATABASE_ID, properties='{"Name": "A"}')

    assert result["status"] == "error"
    assert result["message"].startswith(f"Error retrieving database {DATABASE_ID}")


def test_create_failure_is_an_error(monkeypatch):
    client = _FakeClient(create_error=_http_error(400))

    result = _run(client, monkeypatch, database_id=DATABASE_ID, properties='{"Status": "Nope"}')

    assert result["status"] == "error"
    assert "Error creating record" in result["message"]
    assert "check the database" not in result["message"]


def test_network_failure_on_create_warns_the_record_may_exist(monkeypatch):
    client = _FakeClient(create_error=requests.ReadTimeout("read timed out"))

    result = _run(client, monkeypatch, database_id=DATABASE_ID, properties='{"Name": "A"}')

    assert result["status"] == "error"
    assert "check the database for the record before retrying" in result["message"]

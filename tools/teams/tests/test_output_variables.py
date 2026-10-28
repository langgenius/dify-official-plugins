"""Every tool emits exactly the variables its output_schema declares, with the declared types, on success and on error."""
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
import yaml

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
PY_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "object": dict, "array": list}
TOOL_FILES = sorted(p.stem for p in TOOLS_DIR.glob("*.yaml"))

ITEM = {
    "id": "x1", "displayName": "Name", "description": "d", "webUrl": "https://teams/x1", "email": "a@contoso.com",
    "membershipType": "standard", "chatType": "group", "topic": "T", "lastUpdatedDateTime": "2026-10-01T00:00:00Z",
    "createdDateTime": "2026-10-01T00:00:00Z", "messageType": "message", "subject": "s",
    "body": {"content": "<p>hi</p>", "contentType": "html"}, "from": {"user": {"id": "u1", "displayName": "Kim"}},
    "attachments": [{"name": "f.pdf"}], "members": [{"displayName": "Kim", "userId": "u1", "email": "k@contoso.com"}],
    "userId": "u1", "roles": ["owner"], "title": "Plan", "name": "Bucket", "bucketId": "b1", "percentComplete": 50,
    "dueDateTime": "2026-12-01T00:00:00Z", "assignments": {"u1": {}}, "joinWebUrl": "https://teams/join",
    "startDateTime": "2026-12-01T01:00:00Z", "endDateTime": "2026-12-01T01:30:00Z", "@odata.etag": 'W/"e"',
    "start": {"dateTime": "2026-12-01T10:00:00", "timeZone": "UTC"}, "end": {"dateTime": "2026-12-01T11:00:00", "timeZone": "UTC"},
    "organizer": {"emailAddress": {"name": "Kim", "address": "k@contoso.com"}}, "isOnlineMeeting": True,
    "onlineMeeting": {"joinUrl": "https://teams/join"}, "location": {"displayName": "Room"},
}
# Enough parameters for every tool to reach Microsoft Graph.
PARAMS = {
    "team_id": "t1", "channel_id": "c1", "message_id": "m1", "message": "hi", "chat_id": "19:a@thread.v2", "members": "a@contoso.com",
    "subject": "s", "start_datetime": "2026-12-01T10:00:00+09:00", "end_datetime": "2026-12-01T11:00:00+09:00", "meeting_id": "om1",
    "plan_id": "p1", "task_id": "k1", "title": "Do", "percent_complete": 50,
}
# start_datetime on chat messages needs time_field=lastModifiedDateTime; this test is about outputs.
OVERRIDES = {"list_chat_messages": {"start_datetime": ""}}


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self._payload, self.status_code = payload, status_code
        self.content = b"" if payload is None else json.dumps(payload).encode()
        self.text = self.content.decode()

    def json(self):
        return self._payload


def ok(method, url, **kwargs):
    if method == "DELETE":
        return FakeResponse(None, 204)
    # One body that serves both list endpoints ("value") and single-object endpoints.
    return FakeResponse({**ITEM, "value": [ITEM]}, 201 if method == "POST" else 200)


def fail(method, url, **kwargs):
    return FakeResponse({"error": {"code": "Forbidden", "message": "denied"}}, 403)


def invoke(name, answer, monkeypatch):
    module = importlib.import_module(f"tools.{name}")
    cls = next(v for v in vars(module).values() if isinstance(v, type) and v.__module__ == module.__name__ and hasattr(v, "_invoke"))
    monkeypatch.setattr(requests, "request", answer)
    monkeypatch.setattr(requests, "get", lambda url, **kw: answer("GET", url, **kw))
    monkeypatch.setattr(requests, "post", lambda url, **kw: answer("POST", url, **kw))
    tool = cls.__new__(cls)
    tool.runtime = SimpleNamespace(credentials={"access_token": "t"})
    tool.create_text_message = lambda text: ("text", text)
    tool.create_json_message = lambda data: ("json", data)
    tool.create_variable_message = lambda n, v: ("var", n, v)
    return {m[1]: m[2] for m in tool._invoke({**PARAMS, **OVERRIDES.get(name, {})}) if m[0] == "var"}


def schema(name):
    return yaml.safe_load((TOOLS_DIR / f"{name}.yaml").read_text(encoding="utf-8"))["output_schema"]["properties"]


def test_every_tool_declares_outputs():
    assert len(TOOL_FILES) == 21
    for name in TOOL_FILES:
        assert {"success", "error"} <= set(schema(name)), name


@pytest.mark.parametrize("name", TOOL_FILES)
def test_success_emits_every_declared_variable_with_its_type(name, monkeypatch):
    declared = schema(name)
    emitted = invoke(name, ok, monkeypatch)
    assert set(emitted) == set(declared), name
    for var, spec in declared.items():
        assert isinstance(emitted[var], PY_TYPES[spec["type"].split("[")[0]]), (name, var, emitted[var])
        if spec["type"] == "array" and emitted[var] and spec.get("items", {}).get("properties"):
            # each array item has exactly the declared item fields
            assert set(emitted[var][0]) == set(spec["items"]["properties"]), (name, var)
    assert emitted["success"] is True and emitted["error"] == "", (name, emitted["error"])


@pytest.mark.parametrize("name", TOOL_FILES)
def test_graph_error_still_emits_every_variable(name, monkeypatch):
    emitted = invoke(name, fail, monkeypatch)
    assert set(emitted) == set(schema(name)), name
    assert emitted["success"] is False and "403" in emitted["error"], (name, emitted["error"])


RESERVED = {"text", "json", "files"}  # built-in tool-node outputs; a variable with one of these names breaks the workflow


def test_no_variable_uses_a_reserved_output_name():
    for name in TOOL_FILES:
        assert not set(schema(name)) & RESERVED, (name, set(schema(name)) & RESERVED)

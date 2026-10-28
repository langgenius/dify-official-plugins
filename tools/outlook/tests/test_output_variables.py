"""Every tool emits exactly the variables its output_schema declares, with the declared types, on success and on error."""
import base64
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

ADDR = {"emailAddress": {"name": "Kim", "address": "kim@contoso.com"}}
ITEM = {
    "id": "x1", "subject": "Hello", "name": "a.pdf", "conversationId": "conv1", "webLink": "https://outlook/x1",
    "sender": ADDR, "from": ADDR, "toRecipients": [ADDR], "ccRecipients": [], "bccRecipients": [],
    "receivedDateTime": "2026-10-01T00:00:00Z", "sentDateTime": "2026-10-01T00:00:00Z", "createdDateTime": "2026-10-01T00:00:00Z",
    "lastModifiedDateTime": "2026-10-01T00:00:00Z", "bodyPreview": "hi", "isRead": True, "hasAttachments": False, "importance": "high",
    "body": {"contentType": "html", "content": "<p>hi</p>"}, "isDraft": True, "flag": {"flagStatus": "flagged"},
    "start": {"dateTime": "2026-12-01T10:00:00", "timeZone": "UTC"}, "end": {"dateTime": "2026-12-01T11:00:00", "timeZone": "UTC"},
    "organizer": ADDR, "location": {"displayName": "Room"}, "onlineMeeting": {"joinUrl": "https://teams/join"},
    "owner": {"name": "Kim", "address": "kim@contoso.com"}, "canEdit": True, "isDefaultCalendar": True,
    "@odata.type": "#microsoft.graph.fileAttachment", "contentType": "application/pdf", "size": 3,
    "contentBytes": base64.b64encode(b"pdf").decode(),
    "scheduleId": "kim@contoso.com", "availabilityView": "02",
    "scheduleItems": [{"status": "busy", "start": {"dateTime": "2026-12-01T10:00:00"}, "end": {"dateTime": "2026-12-01T11:00:00"}}],
}
PARAMS = {
    "draft_id": "d1", "event_id": "e1", "message_id": "m1", "attachment_id": "a1", "email_id": "m1", "to": "kim@contoso.com",
    "to_recipients": "kim@contoso.com", "subject": "Hello", "message": "hi", "body": "hi", "priority_level": "high",
    "flag_status": "flagged", "start_datetime": "2026-12-01T10:00:00", "end_datetime": "2026-12-01T11:00:00",
    "emails": "kim@contoso.com", "start_date": "2026-12-01", "end_date": "2026-12-01", "file_to_attach": [SimpleNamespace(blob=b"abc", filename="a.pdf", extension=".pdf", mime_type="application/pdf")],
}


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
    if url.endswith("/sendMail") or url.endswith("/send"):
        return FakeResponse(None, 202)
    return FakeResponse({**ITEM, "value": [ITEM]}, 201 if method == "POST" and "getSchedule" not in url else 200)


def fail(method, url, **kwargs):
    return FakeResponse({"error": {"code": "ErrorAccessDenied", "message": "denied"}}, 403)


def invoke(name, answer, monkeypatch):
    module = importlib.import_module(f"tools.{name}")
    cls = next(v for v in vars(module).values() if isinstance(v, type) and v.__module__ == module.__name__ and hasattr(v, "_invoke"))
    for verb in ("get", "post", "patch", "delete", "put"):
        monkeypatch.setattr(requests, verb, lambda url, _v=verb.upper(), **kw: answer(_v, url, **kw))
    tool = cls.__new__(cls)
    tool.runtime = SimpleNamespace(credentials={"access_token": "t"})
    tool.create_text_message = lambda text: ("text", text)
    tool.create_json_message = lambda data: ("json", data)
    tool.create_blob_message = lambda blob, meta=None: ("blob", blob, meta)
    tool.create_variable_message = lambda n, v: ("var", n, v)
    return {m[1]: m[2] for m in tool._invoke(dict(PARAMS)) if m[0] == "var"}


def schema(name):
    return yaml.safe_load((TOOLS_DIR / f"{name}.yaml").read_text(encoding="utf-8"))["output_schema"]["properties"]


def test_every_tool_declares_outputs():
    assert len(TOOL_FILES) == 19
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
            assert set(emitted[var][0]) == set(spec["items"]["properties"]), (name, var)
    assert emitted["success"] is True and emitted["error"] == "", (name, emitted["error"])


@pytest.mark.parametrize("name", TOOL_FILES)
def test_graph_error_still_emits_every_variable(name, monkeypatch):
    emitted = invoke(name, fail, monkeypatch)
    assert set(emitted) == set(schema(name)), name
    assert emitted["success"] is False and emitted["error"], (name, emitted)


def test_list_messages_variables(monkeypatch):
    emitted = invoke("list_messages", ok, monkeypatch)
    assert emitted["count"] == 1
    assert emitted["messages"][0]["from_address"] == "kim@contoso.com"
    assert emitted["messages"][0]["to"] == ["kim@contoso.com"]
    assert emitted["messages"][0]["web_link"] == "https://outlook/x1"


RESERVED = {"text", "json", "files"}  # built-in tool-node outputs; a variable with one of these names breaks the workflow


def test_no_variable_uses_a_reserved_output_name():
    for name in TOOL_FILES:
        assert not set(schema(name)) & RESERVED, (name, set(schema(name)) & RESERVED)

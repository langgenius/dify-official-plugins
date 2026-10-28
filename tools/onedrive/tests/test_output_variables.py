"""Every tool emits exactly the variables its output_schema declares, with the declared types, on success and on error."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from tools import graph_client
from tools.delete_file_by_id import DeleteFileByIdTool
from tools.get_file_by_id import GetFileByIdTool
from tools.search_file import SearchFileTool
from tools.upload_file import UploadFileTool

TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
PY_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "object": dict, "array": list}
ITEM = {"id": "i1", "name": "a.txt", "size": 3, "file": {"mimeType": "text/plain"}, "webUrl": "https://x/a.txt",
        "@microsoft.graph.downloadUrl": "https://dl/a", "parentReference": {"path": "/drive/root:", "driveId": "d"},
        "lastModifiedDateTime": "2026-10-22T00:00:00Z"}


class FakeResponse:
    def __init__(self, payload=None, status_code=200, content=None):
        self._payload, self.status_code = payload, status_code
        self.content = content if content is not None else (b"" if payload is None else json.dumps(payload).encode())
        self.text = self.content.decode(errors="replace")

    def json(self):
        return self._payload


def invoke(cls, params, routes):
    def fake_request(method, url, headers=None, params=None, data=None, timeout=None):
        for (m, suffix), response in routes.items():
            if m == method and suffix in url:
                return response
        return FakeResponse({"error": {"code": "itemNotFound", "message": "nope"}}, 404)

    tool = cls.__new__(cls)
    tool.runtime = SimpleNamespace(credentials={"access_token": "t"})
    tool.create_text_message = lambda text: ("text", text)
    tool.create_json_message = lambda data: ("json", data)
    tool.create_blob_message = lambda blob, meta: ("blob", blob, meta)
    tool.create_variable_message = lambda name, value: ("var", name, value)
    original = graph_client.requests.request
    graph_client.requests.request = fake_request
    try:
        return {m[1]: m[2] for m in tool._invoke(params) if m[0] == "var"}
    finally:
        graph_client.requests.request = original


def schema(name):
    return yaml.safe_load((TOOLS_DIR / f"{name}.yaml").read_text(encoding="utf-8"))["output_schema"]["properties"]


CASES = [
    (SearchFileTool, "search_file", {"query": "a"}, {("GET", "/search"): FakeResponse({"value": [ITEM]})}),
    (GetFileByIdTool, "get_file_by_id", {"file_id": "i1"}, {("GET", "/items/i1"): FakeResponse(ITEM)}),
    (UploadFileTool, "upload_file", {"file": SimpleNamespace(blob=b"abc", filename="a.txt")}, {("PUT", "/content"): FakeResponse(ITEM, 201)}),
    (DeleteFileByIdTool, "delete_file_by_id", {"file_id": "i1"}, {("DELETE", "/items/i1"): FakeResponse(None, 204)}),
]


@pytest.mark.parametrize("cls, name, params, routes", CASES, ids=[c[1] for c in CASES])
def test_success_emits_every_declared_variable_with_its_type(cls, name, params, routes):
    declared = schema(name)
    emitted = invoke(cls, params, routes)
    assert set(emitted) == set(declared)
    for var, spec in declared.items():
        assert isinstance(emitted[var], PY_TYPES[spec["type"].split("[")[0]]), (name, var, emitted[var])
    assert emitted["success"] is True and emitted["error"] == ""


@pytest.mark.parametrize("cls, name, params, routes", CASES, ids=[c[1] for c in CASES])
def test_graph_error_still_emits_every_variable(cls, name, params, routes):
    emitted = invoke(cls, params, {})
    assert set(emitted) == set(schema(name))
    assert emitted["success"] is False and "404" in emitted["error"]


def test_search_variables_are_flat_and_typed():
    emitted = invoke(SearchFileTool, {"query": "a"}, {("GET", "/search"): FakeResponse({"value": [ITEM, {"id": "f", "name": "dir", "folder": {}}]})})
    assert emitted["count"] == 2
    assert emitted["items"][0] == {"id": "i1", "name": "a.txt", "is_folder": False, "mime_type": "text/plain", "size": 3,
                                   "web_url": "https://x/a.txt", "download_url": "https://dl/a", "path": "/drive/root:",
                                   "last_modified": "2026-10-22T00:00:00Z"}
    assert emitted["items"][1]["is_folder"] is True and emitted["items"][1]["size"] == 0


RESERVED = {"text", "json", "files"}  # built-in tool-node outputs; a variable with one of these names breaks the workflow


def test_no_variable_uses_a_reserved_output_name():
    for path in TOOLS_DIR.glob("*.yaml"):
        names = set(yaml.safe_load(path.read_text(encoding="utf-8"))["output_schema"]["properties"])
        assert not names & RESERVED, (path.name, names & RESERVED)

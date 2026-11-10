"""The operations added in 1.0.0: list folder, create folder, rename, copy, share, text upload."""
import json
from types import SimpleNamespace

import pytest

import tools.onedrive_copy as copy_module
from tools import graph_client
from tools.onedrive_copy import CopyTool
from tools.onedrive_create_folder import CreateFolderTool
from tools.onedrive_list_folder import ListFolderTool
from tools.onedrive_rename import RenameTool
from tools.onedrive_share import ShareTool
from tools.upload_file import UploadFileTool

DRIVE = "https://graph.microsoft.com/v1.0/me/drive"


class FakeResponse:
    def __init__(self, payload=None, status_code=200, headers=None):
        self._payload, self.status_code, self.headers = payload, status_code, headers or {}
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class Graph:
    """Fake requests.request: answers (method, exact URL) and records every call."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, method, url, headers=None, params=None, data=None, timeout=None, json=None):
        self.calls.append(SimpleNamespace(method=method, url=url, headers=headers or {}, params=params, data=data, json=json))
        if (method, url) in self.routes:
            return self.routes[(method, url)]
        return FakeResponse({"error": {"code": "itemNotFound", "message": "nope"}}, 404)


def run(cls, params, routes, monkeypatch):
    graph = Graph(routes)
    monkeypatch.setattr(graph_client.requests, "request", graph)
    tool = cls.__new__(cls)
    tool.runtime = SimpleNamespace(credentials={"access_token": "user-token"})
    tool.create_text_message = lambda text: ("text", text)
    tool.create_json_message = lambda data: ("json", data)
    tool.create_variable_message = lambda name, value: ("var", name, value)
    messages = list(tool._invoke(params))
    out = {m[1]: m[2] for m in messages if m[0] == "var"}
    texts = [m[1] for m in messages if m[0] == "text"]
    return graph, out, texts


def test_list_folder_follows_graph_pages_up_to_the_limit(monkeypatch):
    page2 = f"{DRIVE}/items/f1/children?$skiptoken=abc"
    graph, out, texts = run(ListFolderTool, {"folder_id": "f1", "limit": 3}, {
        ("GET", f"{DRIVE}/items/f1/children"): FakeResponse({"value": [{"id": "a", "name": "a"}, {"id": "b", "name": "b", "folder": {}}], "@odata.nextLink": page2}),
        ("GET", page2): FakeResponse({"value": [{"id": "c", "name": "c"}, {"id": "d", "name": "d"}]}),
    }, monkeypatch)
    assert [i["id"] for i in out["items"]] == ["a", "b", "c"] and out["has_more"] is True
    assert "b (folder" in texts[0]


def test_list_folder_does_not_follow_a_link_to_another_host(monkeypatch):
    graph, out, _ = run(ListFolderTool, {}, {
        ("GET", f"{DRIVE}/root/children"): FakeResponse({"value": [{"id": "a", "name": "a"}], "@odata.nextLink": "https://evil.example/next"}),
    }, monkeypatch)
    assert len(graph.calls) == 1 and out["count"] == 1


def test_create_folder_path_reuses_existing_folders(monkeypatch):
    graph, out, texts = run(CreateFolderTool, {"name": "/Reports/2026/"}, {
        ("GET", f"{DRIVE}/root:/Reports"): FakeResponse({"id": "r1", "name": "Reports", "folder": {}}),
        ("POST", f"{DRIVE}/items/r1/children"): FakeResponse({"id": "y1", "name": "2026", "folder": {}}, 201),
    }, monkeypatch)
    assert out["folder_id"] == "y1" and out["created"] is True
    post = [c for c in graph.calls if c.method == "POST"][0]
    assert post.json == {"name": "2026", "folder": {}, "@microsoft.graph.conflictBehavior": "fail"}


def test_create_folder_refuses_a_file_in_the_way_and_dot_segments(monkeypatch):
    _, out, texts = run(CreateFolderTool, {"name": "notes"}, {
        ("GET", f"{DRIVE}/root:/notes"): FakeResponse({"id": "n1", "name": "notes", "file": {}}),
    }, monkeypatch)
    assert out["success"] is False and "is a file" in texts[0]
    _, out, texts = run(CreateFolderTool, {"name": "a/../b"}, {}, monkeypatch)
    assert out["success"] is False and ".." in texts[0]


def test_rename_sends_the_new_name_and_rejects_slashes(monkeypatch):
    graph, out, _ = run(RenameTool, {"item_id": "i1", "new_name": "q3.pdf"}, {
        ("PATCH", f"{DRIVE}/items/i1"): FakeResponse({"id": "i1", "name": "q3.pdf"}),
    }, monkeypatch)
    assert graph.calls[0].json == {"name": "q3.pdf"} and out["name"] == "q3.pdf"
    graph, out, texts = run(RenameTool, {"item_id": "i1", "new_name": "a/b"}, {}, monkeypatch)
    assert not graph.calls and out["success"] is False


def test_copy_waits_on_the_monitor_without_the_token(monkeypatch):
    monitor = "https://api.onedrive.com/v1.0/monitor/m1"
    polls = []

    def fake_get(url, timeout=None, allow_redirects=None, headers=None):
        polls.append(SimpleNamespace(url=url, headers=headers))
        return FakeResponse({"status": "completed", "resourceId": "c1"})

    monkeypatch.setattr(copy_module.requests, "get", fake_get)
    graph, out, texts = run(CopyTool, {"file_id": "i1", "name": "copy.txt", "parent_folder_id": "f2"}, {
        ("GET", f"{DRIVE}/items/i1"): FakeResponse({"id": "i1", "name": "a.txt", "parentReference": {"driveId": "d1", "id": "f1"}}),
        ("GET", f"{DRIVE}/items/f2"): FakeResponse({"id": "f2", "parentReference": {"driveId": "d1"}}),
        ("POST", f"{DRIVE}/items/i1/copy"): FakeResponse(None, 202, {"Location": monitor}),
        ("GET", f"{DRIVE}/items/c1"): FakeResponse({"id": "c1", "name": "copy.txt", "webUrl": "https://x/c1"}),
    }, monkeypatch)
    post = [c for c in graph.calls if c.method == "POST"][0]
    assert post.json == {"parentReference": {"driveId": "d1", "id": "f2"}, "name": "copy.txt"}
    assert post.params == {"@microsoft.graph.conflictBehavior": "rename"}
    assert polls[0].url == monitor and not polls[0].headers
    assert out["status"] == "completed" and out["file_id"] == "c1"


def test_copy_into_the_same_folder_by_default(monkeypatch):
    graph, out, _ = run(CopyTool, {"file_id": "i1"}, {
        ("GET", f"{DRIVE}/items/i1"): FakeResponse({"id": "i1", "name": "a.txt", "parentReference": {"driveId": "d1", "id": "f1"}}),
        ("POST", f"{DRIVE}/items/i1/copy"): FakeResponse(None, 202),
    }, monkeypatch)
    post = [c for c in graph.calls if c.method == "POST"][0]
    assert post.json == {"parentReference": {"driveId": "d1", "id": "f1"}}
    assert out["status"] == "in_progress" and out["success"] is True


def test_share_defaults_to_a_view_link_for_the_organization(monkeypatch):
    graph, out, texts = run(ShareTool, {"item_id": "i1"}, {
        ("POST", f"{DRIVE}/items/i1/createLink"): FakeResponse({"id": "p1", "link": {"type": "view", "scope": "organization", "webUrl": "https://s/x"}}, 201),
    }, monkeypatch)
    assert graph.calls[0].json == {"type": "view", "scope": "organization"}
    assert out["link_url"] == "https://s/x" and "people in your organization" in texts[0]
    graph, out, texts = run(ShareTool, {"item_id": "i1", "type": "owner"}, {}, monkeypatch)
    assert not graph.calls and out["success"] is False


def test_share_explains_a_refused_link(monkeypatch):
    _, out, texts = run(ShareTool, {"item_id": "i1", "scope": "anonymous"}, {
        ("POST", f"{DRIVE}/items/i1/createLink"): FakeResponse({"error": {"code": "accessDenied", "message": "denied"}}, 403),
    }, monkeypatch)
    assert out["success"] is False and "anonymous links are often turned off" in texts[0]


def test_upload_text_into_a_folder(monkeypatch):
    graph, out, _ = run(UploadFileTool, {"file_content": "héllo", "file_name": "notes.txt", "parent_folder_id": "f1"}, {
        ("PUT", f"{DRIVE}/items/f1:/notes.txt:/content"): FakeResponse({"id": "n1", "name": "notes.txt", "size": 6}, 201),
    }, monkeypatch)
    assert graph.calls[0].data == "héllo".encode("utf-8") and out["file_id"] == "n1"


@pytest.mark.parametrize("params", [{"file_content": "x"}, {}])
def test_upload_needs_a_file_or_text_with_a_name(params, monkeypatch):
    graph, out, _ = run(UploadFileTool, params, {}, monkeypatch)
    assert not graph.calls and out["success"] is False

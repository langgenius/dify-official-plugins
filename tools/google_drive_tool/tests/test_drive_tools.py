import importlib
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from dify_plugin import Tool
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from provider.google_drive_tool import GoogleDriveProvider
from tests.fakes import API, OAUTH, PER_USER, FakeHttp, FakeResponse, make_tool, run
from tools.google_drive_copy_file import GoogleDriveCopyFileTool
from tools.google_drive_delete_file import GoogleDriveDeleteFileTool
from tools.google_drive_download_file import GoogleDriveDownloadFileTool
from tools.google_drive_list_folder import GoogleDriveListFolderTool
from tools.google_drive_move_file import GoogleDriveMoveFileTool
from tools.google_drive_read_text import GoogleDriveReadTextTool
from tools.google_drive_remove_permission import GoogleDriveRemovePermissionTool
from tools.google_drive_search import GoogleDriveSearchTool
from tools.google_drive_share_file import GoogleDriveShareFileTool
from tools.google_drive_sign_out import SignOutTool
from tools.google_drive_upload_file import GoogleDriveUploadFileTool

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = yaml.safe_load((ROOT / "provider" / "google_drive_tool.yaml").read_text(encoding="utf-8"))
DOC = {"id": "d1", "name": "Plan", "mimeType": "application/vnd.google-apps.document", "webViewLink": "https://docs.google.com/d1", "parents": ["root"]}
PDF = {"id": "p1", "name": "a.pdf", "mimeType": "application/pdf", "size": "4", "parents": ["f1"]}


@pytest.fixture
def http(monkeypatch):
    return FakeHttp().install(monkeypatch)


def test_search_builds_an_escaped_query(http):
    http.on("GET", f"{API}/files", {"files": [DOC], "nextPageToken": "n2"}, {"files": [PDF]})
    result = run(make_tool(GoogleDriveSearchTool, OAUTH), {"name": "O'Neil plan", "file_type": "document", "limit": 5})
    q = http.calls[0].params["q"]
    assert q == "trashed = false and name contains 'O\\'Neil plan' and mimeType = 'application/vnd.google-apps.document'"
    assert http.calls[0].params["supportsAllDrives"] == "true" and http.calls[0].params["corpora"] == "allDrives"
    assert http.calls[1].params["pageToken"] == "n2" and result.vars["count"] == 2


def test_search_needs_a_filter(http):
    assert "Give a name" in run(make_tool(GoogleDriveSearchTool, OAUTH), {}).vars["error"]
    http.on("GET", f"{API}/files", {"files": []})
    run(make_tool(GoogleDriveSearchTool, OAUTH), {"recent": True})
    assert http.calls[0].params["q"] == "trashed = false" and http.calls[0].params["orderBy"] == "modifiedTime desc"


def test_list_folder_defaults_to_root(http):
    http.on("GET", f"{API}/files", {"files": [{"id": "f1", "name": "Docs", "mimeType": "application/vnd.google-apps.folder"}]})
    result = run(make_tool(GoogleDriveListFolderTool, OAUTH))
    assert http.calls[0].params["q"] == "'root' in parents and trashed = false" and result.vars["files"][0]["is_folder"]


def test_read_text_exports_docs_as_markdown_with_fallback(http):
    http.on("GET", "/files/d1/export", FakeResponse({"error": {"message": "bad"}}, 400), FakeResponse(None, 200, content=b"plain text"))
    http.on("GET", "/files/d1", DOC)
    result = run(make_tool(GoogleDriveReadTextTool, OAUTH), {"file_id": "d1"})
    exports = [c.params["mimeType"] for c in http.calls if c.url.endswith("/export")]
    assert exports == ["text/markdown", "text/plain"] and result.vars["text"] == "plain text"


def test_read_text_refuses_binary(http):
    http.on("GET", "/files/p1", PDF)
    assert "not text" in run(make_tool(GoogleDriveReadTextTool, OAUTH), {"file_id": "p1"}).vars["error"]


def test_download_binary_and_export(http):
    http.on("GET", "/files/p1", PDF, FakeResponse(None, 200, content=b"%PDF"))
    got = run(make_tool(GoogleDriveDownloadFileTool, OAUTH), {"file_id": "p1"})
    assert got.blobs[0][1] == b"%PDF" and got.blobs[0][2] == {"mime_type": "application/pdf", "filename": "a.pdf"}
    http.routes.clear()
    http.on("GET", "/files/d1/export", FakeResponse(None, 200, content=b"PK.."))
    http.on("GET", "/files/d1", DOC)
    doc = run(make_tool(GoogleDriveDownloadFileTool, OAUTH), {"file_id": "d1"})
    assert doc.vars["name"] == "Plan.docx" and doc.blobs[0][2]["mime_type"].endswith("wordprocessingml.document")
    bad = run(make_tool(GoogleDriveDownloadFileTool, OAUTH), {"file_id": "d1", "export_format": "exe"})
    assert "export_format must be" in bad.vars["error"]


def test_upload_text_as_a_google_sheet(http):
    http.on("POST", "/upload/drive/v3/files", {"id": "s1", "name": "data.csv", "mimeType": "application/vnd.google-apps.spreadsheet"})
    result = run(make_tool(GoogleDriveUploadFileTool, OAUTH), {"text_content": "a,b\n1,2", "name": "data.csv", "folder_id": "f1", "convert_to": "spreadsheet"})
    call = http.calls[0]
    body = call.data.decode()
    assert call.params["uploadType"] == "multipart" and call.headers["Content-Type"].startswith("multipart/related; boundary=")
    assert '"mimeType": "application/vnd.google-apps.spreadsheet"' in body and '"parents": ["f1"]' in body
    assert "Content-Type: text/csv" in body and "a,b\n1,2" in body
    assert result.vars["file_id"] == "s1"
    assert "file name" in run(make_tool(GoogleDriveUploadFileTool, OAUTH), {"text_content": "x"}).vars["error"]


def test_upload_a_file(http):
    http.on("POST", "/upload/drive/v3/files", {"id": "u1", "name": "photo.png"})
    file = SimpleNamespace(blob=b"\x89PNG", filename="photo.png", mime_type="image/png")
    run(make_tool(GoogleDriveUploadFileTool, OAUTH), {"file": file})
    assert b"\x89PNG" in http.calls[0].data and b'"parents": ["root"]' in http.calls[0].data


def test_copy_move_delete(http):
    http.on("POST", "/files/p1/copy", {"id": "p2", "name": "copy"})
    http.on("GET", "/files/p1", PDF)
    http.on("PATCH", "/files/p1", {"id": "p1", "name": "a.pdf", "parents": ["f2"]})
    http.on("DELETE", "/files/p1", FakeResponse(None, 204))
    run(make_tool(GoogleDriveCopyFileTool, OAUTH), {"file_id": "p1", "name": "copy", "folder_id": "f2"})
    assert http.calls[0].json == {"name": "copy", "parents": ["f2"]}
    moved = run(make_tool(GoogleDriveMoveFileTool, OAUTH), {"file_id": "p1", "folder_id": "f2"})
    patch = http.calls[-1]
    assert patch.params["addParents"] == "f2" and patch.params["removeParents"] == "f1" and moved.vars["parents"] == ["f2"]
    run(make_tool(GoogleDriveDeleteFileTool, OAUTH), {"file_id": "p1"})
    assert http.calls[-1].method == "PATCH" and http.calls[-1].json == {"trashed": True}
    run(make_tool(GoogleDriveDeleteFileTool, OAUTH), {"file_id": "p1", "mode": "permanent"})
    assert http.calls[-1].method == "DELETE"


def test_share_and_unshare(http):
    http.on("POST", "/files/d1/permissions", {"id": "perm1", "type": "user", "role": "writer"})
    http.on("GET", "/files/d1/permissions", {"permissions": [{"id": "own", "type": "user", "role": "owner", "emailAddress": "me@x.com"},
                                                             {"id": "perm1", "type": "user", "role": "writer", "emailAddress": "Bob@x.com"},
                                                             {"id": "anyoneWithLink", "type": "anyone", "role": "reader"}]})
    http.on("GET", "/files/d1", DOC)
    http.on("DELETE", "/permissions/", FakeResponse(None, 204))
    shared = run(make_tool(GoogleDriveShareFileTool, OAUTH), {"file_id": "d1", "email": "bob@x.com", "role": "writer", "notify": False})
    assert http.calls[0].json == {"role": "writer", "type": "user", "emailAddress": "bob@x.com"}
    assert http.calls[0].params["sendNotificationEmail"] == "false" and shared.vars["url"] == "https://docs.google.com/d1"
    assert "Give an email" in run(make_tool(GoogleDriveShareFileTool, OAUTH), {"file_id": "d1"}).vars["error"]
    run(make_tool(GoogleDriveRemovePermissionTool, OAUTH), {"file_id": "d1", "email": "bob@x.com"})
    assert http.calls[-1].url.endswith("/files/d1/permissions/perm1")
    run(make_tool(GoogleDriveRemovePermissionTool, OAUTH), {"file_id": "d1", "email": "anyone"})
    assert http.calls[-1].url.endswith("/permissions/anyoneWithLink")
    assert "owner" in run(make_tool(GoogleDriveRemovePermissionTool, OAUTH), {"file_id": "d1", "email": "me@x.com"}).vars["error"]


def test_ids_are_encoded(http):
    run(make_tool(GoogleDriveDeleteFileTool, OAUTH), {"file_id": "../about"})
    assert http.calls[0].url == f"{API}/files/..%2Fabout"


def test_per_user_returns_the_sign_in_link(http):
    result = run(make_tool(GoogleDriveSearchTool, PER_USER), {"name": "x"})
    assert "/google_drive/callback?start=" in result.texts[0] and http.calls == []


def test_sign_out_modes(http):
    assert "only applies" in run(make_tool(SignOutTool, OAUTH)).texts[0]
    assert run(make_tool(SignOutTool, PER_USER)).vars == {"signed_out": False, "success": True, "error": ""}


# ── plugin ────────────────────────────────────────────────────────────


def tool_class(spec):
    module = importlib.import_module(spec["extra"]["python"]["source"][:-3].replace("/", "."))
    classes = [c for _, c in inspect.getmembers(module, inspect.isclass) if issubclass(c, Tool) and c is not Tool]
    assert len(classes) == 1, classes
    return classes[0]


@pytest.mark.parametrize("tool_file", PROVIDER["tools"])
def test_every_tool_loads_and_emits_its_outputs(tool_file, http):
    spec = yaml.safe_load((ROOT / tool_file).read_text(encoding="utf-8"))
    assert spec["identity"]["name"].startswith("google_drive_")
    result = run(make_tool(tool_class(spec), {}))
    assert set(result.vars) == set(spec["output_schema"]["properties"]) and result.vars["success"] is False


def test_manifest_and_endpoint():
    manifest = yaml.safe_load((ROOT / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["name"] == "google_drive_tool" and manifest["plugins"]["endpoints"] == ["group/google_drive_signin.yaml"]
    group = yaml.safe_load((ROOT / "group" / "google_drive_signin.yaml").read_text(encoding="utf-8"))
    assert yaml.safe_load((ROOT / group["endpoints"][0]).read_text(encoding="utf-8"))["path"] == "/google_drive/callback"


def test_provider(http):
    provider = GoogleDriveProvider.__new__(GoogleDriveProvider)
    provider._validate_credentials(PER_USER)
    with pytest.raises(ToolProviderCredentialValidationError, match="/google_drive/callback"):
        provider._validate_credentials({**PER_USER, "redirect_uri": "https://d.example.com/e/x/gmail/callback"})
    http.on("GET", "/drive/v3/about", {"user": {"emailAddress": "a@b.c"}})
    provider._validate_credentials(OAUTH)
    url = provider._oauth_get_authorization_url("https://dify/cb", {"client_id": "cid"})
    assert "auth%2Fdrive" in url and "access_type=offline" in url

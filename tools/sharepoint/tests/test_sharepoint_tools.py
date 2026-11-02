"""Site resolution, URL encoding, output variables, the n8n-parity tools and the provider."""
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
import yaml
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

import provider.sharepoint as provider_module
import tools.graph_client as graph_module
from provider.sharepoint import SharePointProvider

ROOT = Path(__file__).resolve().parents[1]
API = "https://graph.microsoft.com/v1.0"
SID = "contoso.sharepoint.com,g1,g2"
SITE = f"{API}/sites/{SID}"
OAUTH = {"access_token": "user-token"}
SP = {"tenant_id": "contoso.onmicrosoft.com", "client_id": "app", "client_secret": "s3cret"}
PY_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "object": dict, "array": list}
SITE_JSON = {"id": SID, "displayName": "Team", "webUrl": "https://contoso.sharepoint.com/sites/Team"}
ITEM = {"id": "7", "webUrl": "https://x/7", "createdDateTime": "c", "lastModifiedDateTime": "m",
        "fields": {"@odata.etag": "e", "Title": "Q3", "Status": "Draft", "LinkTitle": "Q3", "AuthorLookupId": "9"}}
FILE = {"id": "f1", "name": "a.txt", "size": 3, "file": {"mimeType": "text/plain"}, "webUrl": "https://x/a.txt", "parentReference": {"path": "/drive/root:"},
        "@microsoft.graph.downloadUrl": "https://download.example/a"}


class FakeResponse:
    def __init__(self, payload=None, status_code=200, content=b""):
        self._payload, self.status_code, self.content = payload, status_code, content
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class Graph:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, method, url, headers=None, params=None, timeout=None, json=None, data=None):
        self.calls.append(SimpleNamespace(method=method, url=url, params=params, json=json, data=data, headers=headers or {}))
        if (method, url) in self.routes:
            return self.routes[(method, url)]
        return FakeResponse({"error": {"code": "itemNotFound", "message": "nope"}}, 404)


def run(name, params, routes, monkeypatch, credentials=OAUTH):
    graph = Graph({("GET", SITE): FakeResponse(SITE_JSON), **routes})
    monkeypatch.setattr(graph_module.requests, "request", graph)
    module = importlib.import_module(f"tools.{name}")
    from dify_plugin import Tool
    cls = next(v for v in vars(module).values() if isinstance(v, type) and issubclass(v, Tool) and v is not Tool and v.__module__ == module.__name__)
    tool = cls.__new__(cls)
    tool.runtime = SimpleNamespace(credentials=credentials, user_id="u1")
    tool.create_text_message = lambda text: ("text", text)
    tool.create_json_message = lambda data: ("json", data)
    tool.create_blob_message = lambda blob, meta: ("blob", blob, meta)
    tool.create_variable_message = lambda n, v: ("var", n, v)
    messages = list(tool._invoke(dict(params, site=params.get("site", SID))))
    return graph, {m[1]: m[2] for m in messages if m[0] == "var"}, [m[1] for m in messages if m[0] == "text"], messages


# ── sites ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("site, url", [
    (SID, SITE),
    ("root", f"{API}/sites/root"),
    ("https://contoso.sharepoint.com/sites/Team", f"{API}/sites/contoso.sharepoint.com:/sites/Team:"),
    ("https://contoso.sharepoint.com/sites/Team/Shared%20Documents/Forms/AllItems.aspx", f"{API}/sites/contoso.sharepoint.com:/sites/Team:"),
    ("https://contoso.sharepoint.com/", f"{API}/sites/contoso.sharepoint.com"),
    ("../../me/drive", f"{API}/sites/..%2F..%2Fme%2Fdrive"),
])
def test_site_forms(site, url, monkeypatch):
    graph = Graph({("GET", url): FakeResponse(SITE_JSON)})
    monkeypatch.setattr(graph_module.requests, "request", graph)
    assert graph_module.resolve_site(graph_module.resolve_graph_context(OAUTH), site)["site_id"] == SID


def test_site_urls_must_be_sharepoint():
    with pytest.raises(graph_module.GraphAuthError, match="not a SharePoint host"):
        graph_module.resolve_site(graph_module.resolve_graph_context(OAUTH), "https://evil.example/sites/x")


def test_ids_are_encoded():
    ctx = graph_module.resolve_graph_context(OAUTH)
    assert ctx.item(SID, "Shared/../x", "1?a").endswith(f"/sites/{SID}/lists/Shared%2F..%2Fx/items/1%3Fa")
    assert ctx.drive_item(SID, "") == f"{SITE}/drive/root"


def test_service_principal_needs_no_owner(monkeypatch):
    graph_module._token_cache.clear()
    monkeypatch.setattr(graph_module.requests, "post", lambda *a, **k: FakeResponse({"access_token": "app", "expires_in": 3599}))
    assert graph_module.resolve_graph_context(SP).access_token == "app"


# ── output variables ──────────────────────────────────────────────────

L = f"{SITE}/lists/Tasks"
CASES = {
    "sharepoint_search_sites": ({"query": "team"}, {("GET", f"{API}/sites"): FakeResponse({"value": [SITE_JSON]})}),
    "sharepoint_get_site": ({}, {}),
    "sharepoint_list_lists": ({}, {("GET", f"{SITE}/lists"): FakeResponse({"value": [{"id": "l1", "displayName": "Tasks", "list": {"template": "genericList"}}]})}),
    "sharepoint_get_list": ({"list": "Tasks"}, {("GET", L): FakeResponse({"id": "l1", "displayName": "Tasks", "list": {}, "columns": [
        {"name": "Title", "displayName": "Title", "text": {}, "required": True}, {"name": "Status", "displayName": "Status", "choice": {"choices": ["Draft", "Done"]}}]})}),
    "sharepoint_list_items": ({"list": "Tasks"}, {("GET", f"{L}/items"): FakeResponse({"value": [ITEM]})}),
    "sharepoint_get_item": ({"list": "Tasks", "item_id": "7"}, {("GET", f"{L}/items/7"): FakeResponse(ITEM)}),
    "sharepoint_create_item": ({"list": "Tasks", "fields": '{"Title": "Q3"}'}, {("POST", f"{L}/items"): FakeResponse(ITEM, 201)}),
    "sharepoint_update_item": ({"list": "Tasks", "item_id": "7", "fields": '{"Status": "Done"}'}, {("PATCH", f"{L}/items/7/fields"): FakeResponse({"Status": "Done"})}),
    "sharepoint_upsert_item": ({"list": "Tasks", "match_columns": "Title", "fields": '{"Title": "Q3", "Status": "Done"}'},
                               {("GET", f"{L}/items"): FakeResponse({"value": [ITEM]}), ("PATCH", f"{L}/items/7/fields"): FakeResponse({})}),
    "sharepoint_delete_item": ({"list": "Tasks", "item_id": "7"}, {("DELETE", f"{L}/items/7"): FakeResponse(None, 204)}),
    "sharepoint_list_files": ({}, {("GET", f"{SITE}/drive/root/children"): FakeResponse({"value": [FILE]})}),
    "sharepoint_download_file": ({"file_id": "f1"}, {("GET", f"{SITE}/drive/items/f1"): FakeResponse(FILE)}),
    "sharepoint_upload_file": ({"file_content": "hi", "file_name": "a.txt"}, {("PUT", f"{SITE}/drive/root:/a.txt:/content"): FakeResponse(FILE, 201)}),
    "sharepoint_update_file": ({"file_id": "f1", "new_name": "b.txt"}, {("PATCH", f"{SITE}/drive/items/f1"): FakeResponse(dict(FILE, name="b.txt"))}),
}


def schema(name):
    return yaml.safe_load((ROOT / "tools" / f"{name}.yaml").read_text(encoding="utf-8"))["output_schema"]["properties"]


def test_every_tool_listed_in_the_provider_is_covered():
    tools = yaml.safe_load((ROOT / "provider" / "sharepoint.yaml").read_text(encoding="utf-8"))["tools"]
    assert {Path(t).stem for t in tools} - {"sharepoint_sign_out"} == set(CASES)


@pytest.mark.parametrize("name", sorted(CASES))
def test_success_emits_every_declared_variable_with_its_type(name, monkeypatch):
    params, routes = CASES[name]
    if name == "sharepoint_download_file":
        monkeypatch.setattr(importlib.import_module("tools.sharepoint_download_file").requests, "get", lambda url, timeout=None: FakeResponse(None, 200, b"abc"))
    _, out, _, _ = run(name, params, routes, monkeypatch)
    declared = schema(name)
    assert set(out) == set(declared)
    for var, spec in declared.items():
        assert isinstance(out[var], PY_TYPES[spec["type"]]), (name, var, out[var])
    assert out["success"] is True and out["error"] == ""


@pytest.mark.parametrize("name", sorted(CASES))
def test_graph_error_still_emits_every_variable(name, monkeypatch):
    params, _ = CASES[name]
    graph = Graph({})
    monkeypatch.setattr(graph_module.requests, "request", graph)
    module = importlib.import_module(f"tools.{name}")
    from dify_plugin import Tool
    cls = next(v for v in vars(module).values() if isinstance(v, type) and issubclass(v, Tool) and v is not Tool and v.__module__ == module.__name__)
    tool = cls.__new__(cls)
    tool.runtime = SimpleNamespace(credentials=OAUTH, user_id="u1")
    tool.create_text_message = lambda text: ("text", text)
    tool.create_json_message = lambda data: ("json", data)
    tool.create_variable_message = lambda n, v: ("var", n, v)
    out = {m[1]: m[2] for m in tool._invoke(dict(params, site=SID)) if m[0] == "var"}
    assert set(out) == set(schema(name)) and out["success"] is False and out["error"]


def test_no_tool_hardcodes_the_global_graph_host():
    for path in (ROOT / "tools").glob("*.py"):
        if path.name != "graph_client.py":
            assert "graph.microsoft.com" not in path.read_text(encoding="utf-8"), path.name


# ── behaviour ─────────────────────────────────────────────────────────


def test_items_are_simplified_and_filters_allowed_on_unindexed_columns(monkeypatch):
    graph, out, _, _ = run("sharepoint_list_items", {"list": "Tasks", "filter": "fields/Status eq 'Draft'"}, CASES["sharepoint_list_items"][1], monkeypatch)
    call = graph.calls[-1]
    assert call.params["$filter"] == "fields/Status eq 'Draft'" and call.params["$expand"] == "fields"
    assert call.headers["Prefer"] == "HonorNonIndexedQueriesWarningMayFailRandomly"
    assert out["items"][0]["fields"] == {"Title": "Q3", "Status": "Draft"}


def test_get_list_names_the_columns(monkeypatch):
    _, out, texts, _ = run("sharepoint_get_list", {"list": "Tasks"}, CASES["sharepoint_get_list"][1], monkeypatch)
    assert [c["type"] for c in out["columns"]] == ["text", "choice"] and out["columns"][1]["choices"] == ["Draft", "Done"]
    assert "Title (text, required)" in texts[0]


@pytest.mark.parametrize("matches, expected", [([], "created"), ([ITEM], "updated")])
def test_upsert_creates_or_updates(matches, expected, monkeypatch):
    graph, out, _, _ = run("sharepoint_upsert_item", {"list": "Tasks", "match_columns": "Title, Year", "fields": '{"Title": "O\'Neil", "Year": 2026, "Status": "Done"}'}, {
        ("GET", f"{L}/items"): FakeResponse({"value": matches}),
        ("PATCH", f"{L}/items/7/fields"): FakeResponse({}),
        ("POST", f"{L}/items"): FakeResponse(dict(ITEM, id="8"), 201),
    }, monkeypatch)
    lookup = [c for c in graph.calls if c.method == "GET" and c.url.endswith("/items")][0]
    assert lookup.params["$filter"] == "fields/Title eq 'O''Neil' and fields/Year eq 2026"
    assert out["action"] == expected and out["item_id"] == ("7" if matches else "8")


def test_upsert_refuses_several_matches_and_missing_match_values(monkeypatch):
    _, out, texts, _ = run("sharepoint_upsert_item", {"list": "Tasks", "match_columns": "Title", "fields": '{"Title": "Q3"}'},
                           {("GET", f"{L}/items"): FakeResponse({"value": [ITEM, ITEM]})}, monkeypatch)
    assert out["success"] is False and "More than one item" in texts[0]
    graph, out, texts, _ = run("sharepoint_upsert_item", {"list": "Tasks", "match_columns": "Email", "fields": '{"Title": "Q3"}'}, {}, monkeypatch)
    assert out["success"] is False and "Email" in texts[0]


def test_download_does_not_send_the_token(monkeypatch):
    seen = []
    monkeypatch.setattr(importlib.import_module("tools.sharepoint_download_file").requests, "get",
                        lambda url, timeout=None, **kw: seen.append((url, kw)) or FakeResponse(None, 200, b"abc"))
    _, out, _, messages = run("sharepoint_download_file", {"file_id": "f1"}, CASES["sharepoint_download_file"][1], monkeypatch)
    assert seen == [("https://download.example/a", {})] and ("blob", b"abc", {"file_name": "a.txt", "mime_type": "text/plain"}) in messages


def test_upload_into_a_folder_and_update_both(monkeypatch):
    graph, out, _, _ = run("sharepoint_upload_file", {"file": SimpleNamespace(blob=b"x", filename="r.pdf"), "folder_id": "d1", "file_name": "Q3/r.pdf"},
                           {("PUT", f"{SITE}/drive/items/d1:/Q3/r.pdf:/content"): FakeResponse(FILE, 201)}, monkeypatch)
    assert out["success"] is True and graph.calls[-1].data == b"x"
    graph, out, texts, _ = run("sharepoint_update_file", {"file_id": "f1", "new_name": "b.txt", "file": SimpleNamespace(blob=b"new", filename="z")}, {
        ("PATCH", f"{SITE}/drive/items/f1"): FakeResponse(dict(FILE, name="b.txt")),
        ("PUT", f"{SITE}/drive/items/f1/content"): FakeResponse(dict(FILE, name="b.txt", size=3)),
    }, monkeypatch)
    assert [c.method for c in graph.calls[1:]] == ["PATCH", "PUT"] and "renamed and replaced its content" in texts[0]


def test_update_file_reports_a_rename_that_went_through(monkeypatch):
    _, out, texts, _ = run("sharepoint_update_file", {"file_id": "f1", "new_name": "b.txt", "file": SimpleNamespace(blob=b"new", filename="z")},
                           {("PATCH", f"{SITE}/drive/items/f1"): FakeResponse(dict(FILE, name="b.txt"))}, monkeypatch)
    assert out["success"] is False and "was renamed" in texts[0]


# ── provider ──────────────────────────────────────────────────────────


def test_oauth_urls():
    url = urlparse(SharePointProvider()._oauth_get_authorization_url("https://dify/cb", {"client_id": "c", "tenant_id": "contoso.onmicrosoft.com", "cloud": "china"}))
    assert url.netloc == "login.partner.microsoftonline.cn" and url.path.startswith("/contoso.onmicrosoft.com/")
    assert parse_qs(url.query)["scope"] == ["offline_access https://microsoftgraph.chinacloudapi.cn/User.Read https://microsoftgraph.chinacloudapi.cn/Sites.ReadWrite.All"]


def test_validation_reads_the_root_site(monkeypatch):
    graph_module._token_cache.clear()
    monkeypatch.setattr(graph_module.requests, "post", lambda *a, **k: FakeResponse({"access_token": "app", "expires_in": 3599}))
    monkeypatch.setattr(provider_module.requests, "get", lambda *a, **k: FakeResponse({"error": {}}, 403))
    with pytest.raises(ToolProviderCredentialValidationError, match="Sites.ReadWrite.All"):
        SharePointProvider()._validate_credentials(dict(SP))
    monkeypatch.setattr(provider_module.requests, "get", lambda *a, **k: FakeResponse({"id": "root"}))
    SharePointProvider()._validate_credentials(dict(SP))


PER_USER = dict(SP, auth_mode="per_user", redirect_uri="https://dify.example.com/e/hook/sharepoint/callback")


@pytest.mark.parametrize("redirect_uri, message", [
    ("", "Callback URL"), ("http://localhost/e/h/sharepoint/callback", "localhost"), ("https://d/e/h/todo/callback", "/sharepoint/callback"),
])
def test_per_user_validation_checks_the_callback_url(redirect_uri, message):
    with pytest.raises(ToolProviderCredentialValidationError, match=message):
        SharePointProvider()._validate_credentials(dict(PER_USER, redirect_uri=redirect_uri))


def test_per_user_scope_matches_oauth():
    from tools.user_auth import DELEGATED_SCOPE
    assert set(DELEGATED_SCOPE.split()) == set(SharePointProvider._SCOPE.split())

"""Plugin-level checks: manifest, provider, tool YAMLs, original tools in the new modes, provider validation."""

import importlib
import inspect
import json
from pathlib import Path

import pytest
import requests
import yaml
from dify_plugin import Tool
from dify_plugin.errors.tool import ToolProviderCredentialValidationError, ToolProviderOAuthError
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from provider.confluence import ConfluenceProvider
from tests.fakes import CLOUD_TOKEN, OAUTH, OAUTH_BASE, PER_USER, FakeHttp, FakeResponse, make_tool, run
from tools import atlassian
from tools.create_page import CreatePageTool
from tools.list_space import ListSpaceTool

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = yaml.safe_load((ROOT / "provider" / "confluence.yaml").read_text(encoding="utf-8"))
TOOL_FILES = PROVIDER["tools"]
ORIGINAL = {"create_page", "get_page", "get_space", "list_page_of_space", "list_space", "remove_page"}


@pytest.fixture
def http(monkeypatch):
    return FakeHttp().install(monkeypatch)


def session_send(monkeypatch, payload, status=200, get_payload=None):
    sent = []

    def send(session, request, **kwargs):
        sent.append(request)
        r = requests.Response()
        r.status_code = status
        body = get_payload if get_payload is not None and request.method == "GET" else payload
        r._content = json.dumps(body).encode()
        r.request = request
        r.url = request.url
        return r

    monkeypatch.setattr(requests.Session, "send", send)
    return sent


def test_manifest_declares_endpoint_and_storage():
    manifest = yaml.safe_load((ROOT / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["version"] == "1.0.0"
    assert manifest["plugins"]["endpoints"] == ["group/confluence_signin.yaml"]
    assert manifest["resource"]["permission"]["storage"]["enabled"]
    group = yaml.safe_load((ROOT / "group" / "confluence_signin.yaml").read_text(encoding="utf-8"))
    endpoint = yaml.safe_load((ROOT / group["endpoints"][0]).read_text(encoding="utf-8"))
    assert endpoint["path"] == "/confluence/callback"


def tool_class(spec):
    module = importlib.import_module(spec["extra"]["python"]["source"][:-3].replace("/", "."))
    classes = [c for _, c in inspect.getmembers(module, inspect.isclass) if issubclass(c, Tool) and c is not Tool]
    assert len(classes) == 1, classes
    return classes[0]


@pytest.mark.parametrize("tool_file", TOOL_FILES)
def test_each_tool_yaml_points_to_one_tool_class(tool_file):
    spec = yaml.safe_load((ROOT / tool_file).read_text(encoding="utf-8"))
    assert (ROOT / spec["extra"]["python"]["source"]).exists()
    tool_class(spec)
    for p in spec.get("parameters") or []:
        assert p["form"] in ("llm", "form") and "en_US" in p["label"]


def test_new_tools_are_prefixed_and_names_unique():
    names = [yaml.safe_load((ROOT / f).read_text(encoding="utf-8"))["identity"]["name"] for f in TOOL_FILES]
    assert len(names) == len(set(names))
    assert all(n.startswith("confluence_") for n in names if n not in ORIGINAL)


@pytest.mark.parametrize("tool_file", [f for f in TOOL_FILES if "/confluence_" in f])
def test_new_tools_emit_every_declared_output(tool_file, http):
    spec = yaml.safe_load((ROOT / tool_file).read_text(encoding="utf-8"))
    result = run(make_tool(tool_class(spec), {"url": "", "token": ""}))
    assert set(result.vars) == set(spec["output_schema"]["properties"])
    assert result.vars["success"] is False and result.vars["error"]


def test_original_tools_work_with_oauth(monkeypatch):
    sent = session_send(monkeypatch, {"results": [{"id": "1", "key": "DEV"}], "_links": {}})
    result = run(make_tool(ListSpaceTool, OAUTH))
    assert result.json[0]["spaces"]
    assert sent[0].url.startswith(f"{OAUTH_BASE}/wiki/api/v2/spaces")
    assert sent[0].headers["Authorization"] == "Bearer oauth-token"


def test_original_tool_returns_the_sign_in_link_per_user(http):
    result = run(make_tool(ListSpaceTool, PER_USER))
    assert "https://auth.atlassian.com/authorize?" in result.texts[0]


def test_create_page_with_parent_and_markdown(monkeypatch):
    sent = session_send(monkeypatch, {"id": "77", "title": "T"}, get_payload={"results": [{"id": "9", "key": "DEV"}], "_links": {}})
    result = run(make_tool(CreatePageTool, CLOUD_TOKEN),
                 {"space_key": "DEV", "title": "T", "body": "**hi**", "body_format": "markdown", "parent_id": "50"})
    assert result.texts == ["Page created successfully"] and result.json == [{"id": "77", "title": "T"}]
    post = next(r for r in sent if r.method == "POST")
    payload = json.loads(post.body)
    assert payload["parentId"] == "50" and payload["body"] == {"representation": "storage", "value": "<p><strong>hi</strong></p>"}


# ── provider ──────────────────────────────────────────────────────────


def provider():
    return ConfluenceProvider.__new__(ConfluenceProvider)


def test_validate_token_and_oauth_credentials(http):
    http.on("GET", "https://acme.atlassian.net/wiki/api/v2/spaces", {"results": []})
    provider()._validate_credentials(CLOUD_TOKEN)
    http.on("GET", f"{OAUTH_BASE}/wiki/api/v2/spaces", FakeResponse({}, 401))
    with pytest.raises(ToolProviderCredentialValidationError, match="401"):
        provider()._validate_credentials(OAUTH)
    with pytest.raises(ToolProviderCredentialValidationError, match="required"):
        provider()._validate_credentials({"url": "https://acme.atlassian.net"})


@pytest.mark.parametrize("change, message", [
    ({"client_secret": ""}, "Client Secret"),
    ({"redirect_uri": ""}, "Sign-in Callback URL"),
    ({"redirect_uri": "http://localhost/e/x/confluence/callback"}, "localhost"),
    ({"redirect_uri": "https://dify.example.com/e/x/jira/callback"}, "/confluence/callback"),
])
def test_validate_per_user_fields(change, message):
    with pytest.raises(ToolProviderCredentialValidationError, match=message):
        provider()._validate_credentials({**PER_USER, **change})


def test_oauth_flow(http):
    system = {"client_id": "cid", "client_secret": "sec"}
    url = provider()._oauth_get_authorization_url("https://dify/callback", system)
    assert url.startswith(atlassian.AUTHORIZE_URL) and "read%3Apage%3Aconfluence" in url
    http.on("POST", atlassian.TOKEN_URL, {"access_token": "at", "refresh_token": "rt", "expires_in": 3600})
    http.on("GET", "accessible-resources", [{"id": "cloud-1", "url": "https://acme.atlassian.net", "scopes": ["read:page:confluence"]}])
    http.on("GET", "/ex/confluence/cloud-1/wiki/rest/api/user/current", {"email": "a@acme.com"})
    creds = provider()._oauth_get_credentials("https://dify/callback", system, Request(EnvironBuilder(query_string={"code": "c"}).get_environ()))
    assert creds.credentials["cloud_id"] == "cloud-1" and creds.credentials["account"] == "a@acme.com"
    http.routes.clear()
    http.on("POST", atlassian.TOKEN_URL, FakeResponse({"error": "invalid_grant"}, 403))
    with pytest.raises(ToolProviderOAuthError, match="invalid_grant"):
        provider()._oauth_refresh_credentials("https://dify/callback", system, creds.credentials)

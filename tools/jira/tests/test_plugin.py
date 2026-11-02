"""Plugin-level checks: manifest, provider, tool YAMLs, original tools in the new modes, provider validation."""

import importlib
import inspect
import json
from pathlib import Path

import pytest
import yaml
from dify_plugin import Tool
from dify_plugin.errors.tool import ToolProviderCredentialValidationError, ToolProviderOAuthError
from werkzeug.test import EnvironBuilder
from werkzeug.wrappers import Request

from provider.jira import JiraProvider
from tests.fakes import CLOUD_TOKEN, OAUTH, OAUTH_BASE, PER_USER, FakeHttp, FakeResponse, make_tool, run
from tools import atlassian
from tools.create_issue import CreateIssueTool
from tools.list_project import ListProjectTool

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = yaml.safe_load((ROOT / "provider" / "jira.yaml").read_text(encoding="utf-8"))
TOOL_FILES = PROVIDER["tools"]


@pytest.fixture
def http(monkeypatch):
    return FakeHttp().install(monkeypatch)


def test_manifest_declares_endpoint_and_storage():
    manifest = yaml.safe_load((ROOT / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["version"] == "1.0.0"
    assert manifest["plugins"]["endpoints"] == ["group/jira_signin.yaml"]
    assert manifest["resource"]["permission"]["storage"]["enabled"]
    group = yaml.safe_load((ROOT / "group" / "jira_signin.yaml").read_text(encoding="utf-8"))
    endpoint = yaml.safe_load((ROOT / group["endpoints"][0]).read_text(encoding="utf-8"))
    assert endpoint["path"] == "/jira/callback"


@pytest.mark.parametrize("tool_file", TOOL_FILES)
def test_each_tool_yaml_points_to_one_tool_class(tool_file):
    spec = yaml.safe_load((ROOT / tool_file).read_text(encoding="utf-8"))
    source = spec["extra"]["python"]["source"]
    assert (ROOT / source).exists()
    module = importlib.import_module(source[:-3].replace("/", "."))
    classes = [c for _, c in inspect.getmembers(module, inspect.isclass) if issubclass(c, Tool) and c is not Tool]
    assert len(classes) == 1, classes
    for p in spec.get("parameters") or []:
        assert p["form"] in ("llm", "form") and "en_US" in p["label"]


def test_new_tools_are_prefixed_and_names_unique():
    names = [yaml.safe_load((ROOT / f).read_text(encoding="utf-8"))["identity"]["name"] for f in TOOL_FILES]
    assert len(names) == len(set(names))
    original = {"list_projects", "get_project", "get_recent_projects", "list_boards", "get_board", "list_issues_for_board",
                "get_issue", "create_issue", "delete_issue", "list_issues_type"}
    assert all(n.startswith("jira_") for n in names if n not in original)


@pytest.mark.parametrize("tool_file", [f for f in TOOL_FILES if "/jira_" in f])
def test_new_tools_emit_every_declared_output(tool_file, http):
    """With @with_outputs every output_schema variable is emitted, even when the tool stops early."""
    spec = yaml.safe_load((ROOT / tool_file).read_text(encoding="utf-8"))
    module = importlib.import_module(spec["extra"]["python"]["source"][:-3].replace("/", "."))
    cls = next(c for _, c in inspect.getmembers(module, inspect.isclass) if issubclass(c, Tool) and c is not Tool)
    result = run(make_tool(cls, {"url": "", "token": ""}))
    assert set(result.vars) == set(spec["output_schema"]["properties"])
    assert result.vars["success"] is False and result.vars["error"]


def test_original_tools_work_with_oauth(monkeypatch):
    import requests

    sent = []

    def send(session, request, **kwargs):
        sent.append(request)
        r = requests.Response()
        r.status_code = 200
        # On Cloud the library pages through /project/search.
        r._content = b'{"values": [{"id": "1", "key": "PROJ"}], "isLast": true}'
        r.request = request
        return r

    monkeypatch.setattr(requests.Session, "send", send)
    result = run(make_tool(ListProjectTool, OAUTH))
    assert result.json == [{"projects": [{"id": "1", "key": "PROJ"}]}]
    assert sent[0].url.startswith(f"{OAUTH_BASE}/rest/api/3/project/search")
    assert sent[0].headers["Authorization"] == "Bearer oauth-token"


def test_original_tool_returns_the_sign_in_link_per_user(http):
    result = run(make_tool(ListProjectTool, PER_USER))
    assert "https://auth.atlassian.com/authorize?" in result.texts[0]
    assert http.calls == []


def test_create_issue_accepts_a_key_and_optional_fields(monkeypatch):
    sent = []

    def send(session, request, **kwargs):
        sent.append(request)
        response = FakeResponse({"key": "PROJ-2"}, 201)
        import requests

        r = requests.Response()
        r.status_code = 201
        r._content = response.content
        r.request = request
        return r

    import requests

    monkeypatch.setattr(requests.Session, "send", send)
    result = run(make_tool(CreateIssueTool, CLOUD_TOKEN), {
        "project_key": "PROJ", "issue_type_id": "10002", "summary": "S", "labels": "x", "priority": "High", "assignee": "a1"})
    assert result.json == [{"key": "PROJ-2"}]
    fields = json.loads(sent[0].body)["fields"]
    assert fields["project"] == {"key": "PROJ"}
    assert fields["labels"] == ["x"] and fields["priority"] == {"name": "High"} and fields["assignee"] == {"accountId": "a1"}


# ── provider ──────────────────────────────────────────────────────────


def provider():
    return JiraProvider.__new__(JiraProvider)


def test_validate_token_and_oauth_credentials(http):
    http.on("GET", "https://acme.atlassian.net/rest/api/3/myself", {"accountId": "x"})
    provider()._validate_credentials(CLOUD_TOKEN)
    http.on("GET", f"{OAUTH_BASE}/rest/api/3/myself", FakeResponse({}, 401))
    with pytest.raises(ToolProviderCredentialValidationError, match="401"):
        provider()._validate_credentials(OAUTH)
    with pytest.raises(ToolProviderCredentialValidationError, match="required"):
        provider()._validate_credentials({"url": "https://acme.atlassian.net"})


@pytest.mark.parametrize("change, message", [
    ({"client_secret": ""}, "Client Secret"),
    ({"redirect_uri": ""}, "Sign-in Callback URL"),
    ({"redirect_uri": "http://localhost/e/x/jira/callback"}, "localhost"),
    ({"redirect_uri": "https://dify.example.com/e/x/outlook/callback"}, "/jira/callback"),
])
def test_validate_per_user_fields(change, message):
    with pytest.raises(ToolProviderCredentialValidationError, match=message):
        provider()._validate_credentials({**PER_USER, **change})


def test_validate_per_user_ok_without_network(http):
    provider()._validate_credentials(PER_USER)
    assert http.calls == []


def test_oauth_flow(http):
    system = {"client_id": "cid", "client_secret": "sec", "site_url": "acme.atlassian.net"}
    url = provider()._oauth_get_authorization_url("https://dify/callback", system)
    assert url.startswith(atlassian.AUTHORIZE_URL) and "audience=api.atlassian.com" in url

    http.on("POST", atlassian.TOKEN_URL, {"access_token": "at", "refresh_token": "rt", "expires_in": 3600})
    http.on("GET", "accessible-resources", [{"id": "cloud-1", "url": "https://acme.atlassian.net", "scopes": ["read:jira-work"]}])
    http.on("GET", "/ex/jira/cloud-1/rest/api/3/myself", {"emailAddress": "a@acme.com"})
    request = Request(EnvironBuilder(query_string={"code": "c1"}).get_environ())
    creds = provider()._oauth_get_credentials("https://dify/callback", system, request)
    assert creds.credentials == {"access_token": "at", "refresh_token": "rt", "cloud_id": "cloud-1",
                                 "site_url": "https://acme.atlassian.net", "account": "a@acme.com"}
    assert http.calls[0].json["code"] == "c1" and http.calls[0].json["client_secret"] == "sec"

    http.routes.clear()
    http.on("POST", atlassian.TOKEN_URL, {"access_token": "at2", "refresh_token": "rt2", "expires_in": 3600})
    refreshed = provider()._oauth_refresh_credentials("https://dify/callback", system, creds.credentials)
    assert refreshed.credentials["access_token"] == "at2" and refreshed.credentials["refresh_token"] == "rt2"
    assert refreshed.credentials["cloud_id"] == "cloud-1"

    http.routes.clear()
    http.on("POST", atlassian.TOKEN_URL, FakeResponse({"error": "invalid_grant"}, 403))
    with pytest.raises(ToolProviderOAuthError, match="invalid_grant"):
        provider()._oauth_refresh_credentials("https://dify/callback", system, creds.credentials)

    denied = Request(EnvironBuilder(query_string={"error": "access_denied"}).get_environ())
    with pytest.raises(ToolProviderOAuthError, match="access_denied"):
        provider()._oauth_get_credentials("https://dify/callback", system, denied)

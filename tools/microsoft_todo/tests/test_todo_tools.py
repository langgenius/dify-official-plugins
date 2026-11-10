"""Graph context (incl. pre-1.0.0 authorizations), output variables, the 1.0.0 tools and the provider."""
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
import yaml
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

import provider.microsoft_todo as provider_module
import tools.graph_client as graph_module
from provider.microsoft_todo import MicrosoftTodoProvider

ROOT = Path(__file__).resolve().parents[1]
TODO = "https://graph.microsoft.com/v1.0/me/todo"
OAUTH = {"access_token": "user-token"}
LEGACY = {"token": json.dumps({"access_token": "old-token", "refresh_token": "old-refresh", "expires_at": 1}),
          "client_id": "app", "client_secret": "s3cret"}
SP = {"tenant_id": "contoso.onmicrosoft.com", "client_id": "app", "client_secret": "s3cret"}
PY_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "object": dict, "array": list}
TASK = {"id": "t1", "title": "Pay rent", "status": "notStarted", "importance": "high", "body": {"content": "by bank"},
        "dueDateTime": {"dateTime": "2026-11-05T00:00:00.0000000", "timeZone": "UTC"},
        "createdDateTime": "2026-10-30T01:02:03.1234567Z", "isReminderOn": False}
LIST = {"id": "l1", "displayName": "Tasks", "isOwner": True, "isShared": False}
RES = {"id": "r1", "displayName": "Invoice mail", "applicationName": "Outlook", "externalId": "m1", "webUrl": "https://outlook/m1"}


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self._payload, self.status_code = payload, status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class Graph:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, method, url, headers=None, params=None, timeout=None, json=None):
        self.calls.append(SimpleNamespace(method=method, url=url, params=params, json=json, headers=headers or {}))
        if (method, url) in self.routes:
            return self.routes[(method, url)]
        return FakeResponse({"error": {"code": "ErrorItemNotFound", "message": "nope"}}, 404)


def run(name, params, routes, monkeypatch, credentials=OAUTH):
    graph = Graph(routes)
    monkeypatch.setattr(graph_module.requests, "request", graph)
    module = importlib.import_module(f"tools.{name}")
    from dify_plugin import Tool
    cls = next(v for v in vars(module).values() if isinstance(v, type) and issubclass(v, Tool) and v is not Tool and v.__module__ == module.__name__)
    tool = cls.__new__(cls)
    tool.runtime = SimpleNamespace(credentials=credentials, user_id="u1")
    tool.create_text_message = lambda text: ("text", text)
    tool.create_json_message = lambda data: ("json", data)
    tool.create_variable_message = lambda n, v: ("var", n, v)
    messages = list(tool._invoke(params))
    return graph, {m[1]: m[2] for m in messages if m[0] == "var"}, [m[1] for m in messages if m[0] == "text"], [m[1] for m in messages if m[0] == "json"]


# ── context ───────────────────────────────────────────────────────────


def test_pre_1_0_authorizations_keep_working():
    ctx = graph_module.resolve_graph_context(LEGACY)
    assert ctx.access_token == "old-token" and ctx.todo_base == TODO
    # Their client_secret is not mistaken for a Service Principal.
    assert not graph_module.is_service_principal(LEGACY) and not graph_module.is_per_user(LEGACY)


def test_ids_are_encoded_and_hosts_checked():
    ctx = graph_module.resolve_graph_context(OAUTH)
    assert ctx.linked_resource("../../users/x", "t/1", "r?1").endswith("/lists/..%2F..%2Fusers%2Fx/tasks/t%2F1/linkedResources/r%3F1")
    with pytest.raises(graph_module.GraphAuthError, match="Unsupported"):
        graph_module.resolve_graph_context(dict(OAUTH, graph_base_url="https://evil.example"))
    assert graph_module.resolve_graph_context(dict(OAUTH, graph_base_url="https://graph.microsoft.us")).todo_base == "https://graph.microsoft.us/v1.0/me/todo"


def test_service_principal_needs_a_task_owner(monkeypatch):
    graph_module._token_cache.clear()
    monkeypatch.setattr(graph_module.requests, "post", lambda *a, **k: FakeResponse({"access_token": "app", "expires_in": 3599}))
    with pytest.raises(graph_module.GraphAuthError, match="Task Owner"):
        graph_module.resolve_graph_context(SP)
    assert graph_module.resolve_graph_context(dict(SP, task_user="alice@contoso.com")).todo_base.endswith("/users/alice@contoso.com/todo")
    assert graph_module.resolve_graph_context(SP, task_user="bob@contoso.com").todo_base.endswith("/users/bob@contoso.com/todo")
    with pytest.raises(graph_module.GraphAuthError, match="Service Principal"):
        graph_module.resolve_graph_context(OAUTH, task_user="bob@contoso.com")


# ── output variables of every tool ────────────────────────────────────

T1 = f"{TODO}/lists/l1/tasks/t1"
CASES = {
    "get_lists": ({}, {("GET", f"{TODO}/lists"): FakeResponse({"value": [LIST]})}),
    "get_tasks": ({}, {("GET", f"{TODO}/lists"): FakeResponse({"value": [LIST]})}),
    "get_list_by_id": ({"list_id": "l1"}, {("GET", f"{TODO}/lists/l1"): FakeResponse(LIST)}),
    "get_all_tasks": ({}, {("GET", f"{TODO}/lists"): FakeResponse({"value": [LIST]}), ("GET", f"{TODO}/lists/l1/tasks"): FakeResponse({"value": [TASK]})}),
    "get_tasks_by_list_id": ({"list_id": "l1"}, {("GET", f"{TODO}/lists/l1/tasks"): FakeResponse({"value": [TASK]})}),
    "get_task_by_id": ({"list_id": "l1", "task_id": "t1"}, {("GET", T1): FakeResponse(TASK)}),
    "create_task": ({"list_id": "l1", "title": "Pay rent"}, {("POST", f"{TODO}/lists/l1/tasks"): FakeResponse(TASK, 201)}),
    "complete_task": ({"list_id": "l1", "task_id": "t1"}, {("PATCH", T1): FakeResponse(dict(TASK, status="completed"))}),
    "todo_create_list": ({"display_name": "Trip"}, {("POST", f"{TODO}/lists"): FakeResponse(LIST, 201)}),
    "todo_update_list": ({"list_id": "l1", "display_name": "Trip"}, {("PATCH", f"{TODO}/lists/l1"): FakeResponse(LIST)}),
    "todo_delete_list": ({"list_id": "l1"}, {("DELETE", f"{TODO}/lists/l1"): FakeResponse(None, 204)}),
    "todo_update_task": ({"list_id": "l1", "task_id": "t1", "importance": "low"}, {("PATCH", T1): FakeResponse(TASK)}),
    "todo_delete_task": ({"list_id": "l1", "task_id": "t1"}, {("DELETE", T1): FakeResponse(None, 204)}),
    "todo_list_linked_resources": ({"list_id": "l1", "task_id": "t1"}, {("GET", f"{T1}/linkedResources"): FakeResponse({"value": [RES]})}),
    "todo_get_linked_resource": ({"list_id": "l1", "task_id": "t1", "linked_resource_id": "r1"}, {("GET", f"{T1}/linkedResources/r1"): FakeResponse(RES)}),
    "todo_create_linked_resource": ({"list_id": "l1", "task_id": "t1", "application_name": "Outlook"}, {("POST", f"{T1}/linkedResources"): FakeResponse(RES, 201)}),
    "todo_update_linked_resource": ({"list_id": "l1", "task_id": "t1", "linked_resource_id": "r1", "display_name": "x"}, {("PATCH", f"{T1}/linkedResources/r1"): FakeResponse(RES)}),
    "todo_delete_linked_resource": ({"list_id": "l1", "task_id": "t1", "linked_resource_id": "r1"}, {("DELETE", f"{T1}/linkedResources/r1"): FakeResponse(None, 204)}),
}


def schema(name):
    return yaml.safe_load((ROOT / "tools" / f"{name}.yaml").read_text(encoding="utf-8"))["output_schema"]["properties"]


def test_every_tool_listed_in_the_provider_is_covered():
    tools = yaml.safe_load((ROOT / "provider" / "microsoft_todo.yaml").read_text(encoding="utf-8"))["tools"]
    assert {Path(t).stem for t in tools} - {"todo_sign_out"} == set(CASES)


@pytest.mark.parametrize("name", sorted(CASES))
def test_success_emits_every_declared_variable_with_its_type(name, monkeypatch):
    params, routes = CASES[name]
    _, out, _, _ = run(name, params, routes, monkeypatch)
    declared = schema(name)
    assert set(out) == set(declared)
    for var, spec in declared.items():
        assert isinstance(out[var], PY_TYPES[spec["type"]]), (name, var, out[var])
    assert out["success"] is True and out["error"] == ""


@pytest.mark.parametrize("name", sorted(CASES))
def test_graph_error_still_emits_every_variable(name, monkeypatch):
    params, _ = CASES[name]
    _, out, _, _ = run(name, params, {}, monkeypatch)
    assert set(out) == set(schema(name)) and out["success"] is False and out["error"]


def test_no_tool_hardcodes_the_global_graph_host_or_uses_the_old_libraries():
    for path in (ROOT / "tools").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "pymstodo" not in text and "dify_easy" not in text, path.name
        if path.name != "graph_client.py":
            assert "graph.microsoft.com" not in text, path.name


# ── behaviour ─────────────────────────────────────────────────────────


def test_outputs_keep_the_pre_1_0_shape(monkeypatch):
    _, _, texts, jsons = run("get_tasks_by_list_id", {"list_id": "l1"}, CASES["get_tasks_by_list_id"][1], monkeypatch)
    task = jsons[0]["data"][0]
    assert {k: task[k] for k in ("task_id", "title", "status", "body_text", "due_date", "created_date")} == {
        "task_id": "t1", "title": "Pay rent", "status": "notStarted", "body_text": "by bank",
        "due_date": "2026-11-05 00:00:00+00:00", "created_date": "2026-10-30 01:02:03.123456+00:00"}
    assert texts[0].startswith("[{'task_id': 't1'")
    _, _, _, jsons = run("get_tasks", {}, CASES["get_tasks"][1], monkeypatch)
    assert jsons[0] == {"data": [{"list_id": "l1", "display_name": "Tasks", "is_owner": True, "is_shared": False, "link": "href=https://to-do.live.com/tasks/l1"}]}


@pytest.mark.parametrize("status_filter, expected", [(None, "status ne 'completed'"), ("completed", "status eq 'completed'"), ("all", None)])
def test_tasks_are_not_completed_ones_by_default(status_filter, expected, monkeypatch):
    params = {"list_id": "l1", **({"status_filter": status_filter} if status_filter else {})}
    graph, _, _, _ = run("get_tasks_by_list_id", params, CASES["get_tasks_by_list_id"][1], monkeypatch)
    assert graph.calls[0].params.get("$filter") == expected


def test_paging_stays_on_the_graph_host(monkeypatch):
    graph, out, _, _ = run("get_tasks_by_list_id", {"list_id": "l1", "status_filter": "all"}, {
        ("GET", f"{TODO}/lists/l1/tasks"): FakeResponse({"value": [TASK], "@odata.nextLink": "https://evil.example/next"}),
    }, monkeypatch)
    assert len(graph.calls) == 1 and out["count"] == 1


def test_create_task_with_optional_fields(monkeypatch):
    graph, out, _, _ = run("create_task", {"list_id": "l1", "title": "Call Kim", "due_date": "2026-11-05", "body_text": "re: Q3",
                                            "reminder_datetime": "2026-11-04T09:00:00+09:00", "importance": "high", "status": "inProgress"},
                           {("POST", f"{TODO}/lists/l1/tasks"): FakeResponse(TASK, 201)}, monkeypatch)
    assert graph.calls[0].json == {
        "title": "Call Kim", "body": {"content": "re: Q3", "contentType": "text"},
        "dueDateTime": {"dateTime": "2026-11-05T00:00:00.0000000", "timeZone": "UTC"},
        "reminderDateTime": {"dateTime": "2026-11-04T00:00:00.0000000", "timeZone": "UTC"}, "isReminderOn": True,
        "importance": "high", "status": "inProgress"}


@pytest.mark.parametrize("params, message", [
    ({"importance": "urgent"}, "importance"), ({"status": "done"}, "status"), ({"due_date": "next week"}, "due_date"), ({}, "at least one field"),
])
def test_update_task_validates_fields(params, message, monkeypatch):
    graph, out, texts, _ = run("todo_update_task", {"list_id": "l1", "task_id": "t1", **params}, {}, monkeypatch)
    assert not graph.calls and out["success"] is False and message in texts[0]


def test_linked_resource_fields_and_url_check(monkeypatch):
    graph, out, _, _ = run("todo_create_linked_resource", {"list_id": "l1", "task_id": "t1", "application_name": "Jira", "external_id": "PRJ-1",
                                                           "web_url": "https://jira/PRJ-1"}, {("POST", f"{T1}/linkedResources"): FakeResponse(RES, 201)}, monkeypatch)
    assert graph.calls[0].json == {"applicationName": "Jira", "externalId": "PRJ-1", "webUrl": "https://jira/PRJ-1"}
    graph, out, texts, _ = run("todo_create_linked_resource", {"list_id": "l1", "task_id": "t1", "application_name": "Jira", "web_url": "javascript:alert(1)"}, {}, monkeypatch)
    assert not graph.calls and "https://" in texts[0]


def test_service_principal_tools_use_the_task_owner(monkeypatch):
    graph_module._token_cache.clear()
    monkeypatch.setattr(graph_module.requests, "post", lambda *a, **k: FakeResponse({"access_token": "app", "expires_in": 3599}))
    users = "https://graph.microsoft.com/v1.0/users/alice@contoso.com/todo"
    graph, out, _, _ = run("get_lists", {}, {("GET", f"{users}/lists"): FakeResponse({"value": [LIST]})}, monkeypatch,
                           credentials=dict(SP, task_user="alice@contoso.com"))
    assert out["count"] == 1 and graph.calls[0].headers["Authorization"] == "Bearer app"


# ── provider ──────────────────────────────────────────────────────────


def test_oauth_tenant_cloud_and_old_scopes():
    url = urlparse(MicrosoftTodoProvider()._oauth_get_authorization_url("https://dify/cb", {"client_id": "c"}))
    assert url.netloc == "login.microsoftonline.com" and url.path.startswith("/common/")
    assert parse_qs(url.query)["scope"] == ["openid offline_access Tasks.ReadWrite"]
    url = urlparse(MicrosoftTodoProvider()._oauth_get_authorization_url("https://dify/cb", {"client_id": "c", "tenant_id": "contoso.onmicrosoft.com", "cloud": "usgov"}))
    assert url.netloc == "login.microsoftonline.us" and parse_qs(url.query)["scope"] == ["openid offline_access https://graph.microsoft.us/Tasks.ReadWrite"]


def test_refresh_reads_a_pre_1_0_token_and_moves_to_the_new_fields(monkeypatch):
    sent = []
    monkeypatch.setattr(provider_module.requests, "post", lambda url, data=None, timeout=None: sent.append(data) or FakeResponse({"access_token": "new", "expires_in": 3599}))
    result = MicrosoftTodoProvider()._oauth_refresh_credentials("https://dify/cb", {"client_id": "c", "client_secret": "s"}, LEGACY)
    assert sent[0]["refresh_token"] == "old-refresh" and "scope" not in sent[0]
    assert result.credentials == {"access_token": "new", "refresh_token": "old-refresh", "graph_base_url": "https://graph.microsoft.com"}


def test_validation_never_puts_secrets_in_the_message(monkeypatch):
    monkeypatch.setattr(provider_module.requests, "get", lambda *a, **k: FakeResponse({"error": {}}, 403))
    with pytest.raises(ToolProviderCredentialValidationError) as exc:
        MicrosoftTodoProvider()._validate_credentials(dict(LEGACY))
    assert "s3cret" not in str(exc.value) and "old-token" not in str(exc.value) and "old-refresh" not in str(exc.value)
    monkeypatch.setattr(provider_module.requests, "get", lambda *a, **k: FakeResponse({"value": []}))
    MicrosoftTodoProvider()._validate_credentials(dict(LEGACY))  # a working token passes (it used to always fail)


PER_USER = dict(SP, auth_mode="per_user", redirect_uri="https://dify.example.com/e/hook/todo/callback")


@pytest.mark.parametrize("redirect_uri, message", [
    ("", "Callback URL"), ("http://localhost/e/h/todo/callback", "localhost"), ("https://d/e/h/excel/callback", "/todo/callback"),
])
def test_per_user_validation_checks_the_callback_url(redirect_uri, message):
    with pytest.raises(ToolProviderCredentialValidationError, match=message):
        MicrosoftTodoProvider()._validate_credentials(dict(PER_USER, redirect_uri=redirect_uri))


def test_per_user_scope_covers_the_oauth_scope():
    from tools.user_auth import DELEGATED_SCOPE
    assert set(MicrosoftTodoProvider._SCOPE.split()) <= set(DELEGATED_SCOPE.split())

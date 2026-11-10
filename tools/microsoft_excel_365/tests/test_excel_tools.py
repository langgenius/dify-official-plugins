"""Graph context, URL encoding, output variables and the 1.0.0 tools."""
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
import yaml

import tools.graph_client as graph_module
from provider.microsoft_excel365 import Excel365Provider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

ROOT = Path(__file__).resolve().parents[1]
ME = "https://graph.microsoft.com/v1.0/me/drive"
WB = f"{ME}/items/wb1/workbook"
OAUTH = {"access_token": "user-token"}
SP = {"tenant_id": "contoso.onmicrosoft.com", "client_id": "app", "client_secret": "s3cret"}
PY_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "object": dict, "array": list}


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self._payload, self.status_code = payload, status_code
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class Graph:
    """Fake requests.request: answers (method, exact URL) and records every call."""

    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, method, url, headers=None, params=None, timeout=None, json=None):
        self.calls.append(SimpleNamespace(method=method, url=url, params=params, json=json))
        if (method, url) in self.routes:
            answer = self.routes[(method, url)]
            return answer(self.calls[-1]) if callable(answer) else answer
        return FakeResponse({"error": {"code": "ItemNotFound", "message": "nope"}}, 404)


def tool_class(name):
    module = importlib.import_module(f"tools.{name}")
    from dify_plugin import Tool
    return next(v for v in vars(module).values() if isinstance(v, type) and issubclass(v, Tool) and v is not Tool and v.__module__ == module.__name__)


def run(name, params, routes, monkeypatch, credentials=OAUTH):
    graph = Graph(routes)
    monkeypatch.setattr(graph_module.requests, "request", graph)
    cls = tool_class(name)
    tool = cls.__new__(cls)
    tool.runtime = SimpleNamespace(credentials=credentials, user_id="u1")
    tool.create_text_message = lambda text: ("text", text)
    tool.create_json_message = lambda data: ("json", data)
    tool.create_variable_message = lambda n, v: ("var", n, v)
    messages = list(tool._invoke(params))
    return graph, {m[1]: m[2] for m in messages if m[0] == "var"}, [m[1] for m in messages if m[0] == "text"]


# ── context and encoding ──────────────────────────────────────────────


def test_oauth_site_and_names_are_encoded():
    ctx = graph_module.resolve_graph_context(OAUTH, site_id="contoso.sharepoint.com,g1,g2")
    assert ctx.drive_base == "https://graph.microsoft.com/v1.0/sites/contoso.sharepoint.com,g1,g2/drive"
    # A sheet name with a quote or slash, or an ID trying to climb the path, stays one segment.
    assert ctx.worksheet("../users/x", "Q3's/plan").endswith("/items/..%2Fusers%2Fx/workbook/worksheets/Q3%27s%2Fplan")
    assert ctx.range("wb1", "S", "A1:B2'") .endswith("/range(address=%27A1%3AB2%27%27%27)")
    assert graph_module.resolve_graph_context(OAUTH, site_id="a/../../me").drive_base.endswith("/sites/a%2F..%2F..%2Fme/drive")


def test_oauth_national_cloud_and_unknown_hosts():
    ctx = graph_module.resolve_graph_context(dict(OAUTH, graph_base_url="https://graph.microsoft.us"))
    assert ctx.drive_base == "https://graph.microsoft.us/v1.0/me/drive"
    with pytest.raises(graph_module.GraphAuthError, match="Unsupported"):
        graph_module.resolve_graph_context(dict(OAUTH, graph_base_url="https://evil.example"))
    with pytest.raises(graph_module.GraphAuthError, match="Service Principal"):
        graph_module.resolve_graph_context(OAUTH, drive_user="bob@contoso.com")


def test_service_principal_needs_a_drive_owner_or_site(monkeypatch):
    graph_module._token_cache.clear()
    monkeypatch.setattr(graph_module.requests, "post", lambda *a, **k: FakeResponse({"access_token": "app", "expires_in": 3599}))
    with pytest.raises(graph_module.GraphAuthError, match="Drive Owner"):
        graph_module.resolve_graph_context(SP)
    assert graph_module.resolve_graph_context(dict(SP, drive_user="alice@contoso.com")).drive_base.endswith("/users/alice@contoso.com/drive")
    assert graph_module.resolve_graph_context(SP, drive_user="bob@contoso.com").drive_base.endswith("/users/bob@contoso.com/drive")
    assert graph_module.resolve_graph_context(SP, site_id="s,1,2").drive_base.endswith("/sites/s,1,2/drive")


# ── output variables of every tool ────────────────────────────────────

ITEM = {"id": "f1", "name": "Q3.xlsx", "file": {}, "size": 10, "lastModifiedDateTime": "t", "webUrl": "https://x", "parentReference": {"path": "/drive/root:"}}
USED = f"{WB}/worksheets/Sheet1/usedRange(valuesOnly=true)"
TABLE = f"{WB}/tables/Sales"
CASES = {
    "list_all_files": ({}, {("GET", f"{ME}/root/children"): FakeResponse({"value": [ITEM]})}),
    "list_workbooks": ({"search_query": "Q3"}, {("GET", f"{ME}/root/search(q=%27Q3%27)"): FakeResponse({"value": [ITEM]})}),
    "list_worksheets": ({"workbook_id": "wb1"}, {("GET", f"{WB}/worksheets"): FakeResponse({"value": [{"id": "s1", "name": "Sheet1", "position": 0}]})}),
    "create_worksheet": ({"workbook_id": "wb1", "worksheet_name": "New"}, {("POST", f"{WB}/worksheets"): FakeResponse({"id": "s2", "name": "New", "position": 1})}),
    "read_worksheet_data": ({"workbook_id": "wb1", "worksheet_name": "Sheet1", "range": "A1:B2"},
                            {("GET", f"{WB}/worksheets/Sheet1/range(address=%27A1%3AB2%27)"): FakeResponse({"values": [[1, 2]], "rowCount": 1, "columnCount": 2, "address": "Sheet1!A1:B1"})}),
    "write_worksheet_data": ({"workbook_id": "wb1", "worksheet_name": "Sheet1", "range": "A1", "values": '[["x"]]'},
                             {("PATCH", f"{WB}/worksheets/Sheet1/range(address=%27A1%27)"): FakeResponse({"rowCount": 1, "columnCount": 1, "address": "Sheet1!A1"})}),
    "clear_worksheet_data": ({"workbook_id": "wb1", "worksheet_name": "Sheet1", "range": "A1:B2"},
                             {("POST", f"{WB}/worksheets/Sheet1/range(address=%27A1%3AB2%27)/clear"): FakeResponse({})}),
    "search_worksheet_data": ({"workbook_id": "wb1", "worksheet_name": "Sheet1", "search_value": "kim"},
                              {("GET", f"{WB}/worksheets/Sheet1/range(address=%27A1%3AZ1000%27)"): FakeResponse({"values": [["Kim"]], "address": "Sheet1!A1:Z1000"})}),
    "excel_delete_workbook": ({"workbook_id": "wb1"}, {("DELETE", f"{ME}/items/wb1"): FakeResponse(None, 204)}),
    "excel_delete_worksheet": ({"workbook_id": "wb1", "worksheet_name": "Sheet1"}, {("DELETE", f"{WB}/worksheets/Sheet1"): FakeResponse(None, 204)}),
    "excel_append_rows": ({"workbook_id": "wb1", "worksheet_name": "Sheet1", "rows": '[{"Name": "Lee"}]'},
                          {("GET", USED): FakeResponse({"address": "Sheet1!A1:B2", "values": [["Name", "Score"], ["Kim", 90]]}),
                           ("PATCH", f"{WB}/worksheets/Sheet1/range(address=%27A3%3AB3%27)"): FakeResponse({"address": "Sheet1!A3:B3"})}),
    "excel_upsert_rows": ({"workbook_id": "wb1", "worksheet_name": "Sheet1", "key_column": "Name", "rows": '[{"Name": "Kim", "Score": 95}]'},
                          {("GET", USED): FakeResponse({"address": "Sheet1!A1:B2", "values": [["Name", "Score"], ["Kim", 90]]}),
                           ("PATCH", f"{WB}/worksheets/Sheet1/range(address=%27A2%3AB2%27)"): FakeResponse({})}),
    "excel_list_tables": ({"workbook_id": "wb1"}, {("GET", f"{WB}/tables"): FakeResponse({"value": [{"id": "t1", "name": "Sales", "showHeaders": True, "worksheet": {"name": "Sheet1"}}]})}),
    "excel_add_table": ({"workbook_id": "wb1", "worksheet_name": "Sheet1", "range": "A1:B5"}, {("POST", f"{WB}/tables/add"): FakeResponse({"id": "t1", "name": "Table1"})}),
    "excel_delete_table": ({"workbook_id": "wb1", "table": "Sales"}, {("DELETE", TABLE): FakeResponse(None, 204)}),
    "excel_convert_table_to_range": ({"workbook_id": "wb1", "table": "Sales"}, {("POST", f"{TABLE}/convertToRange"): FakeResponse({"address": "Sheet1!A1:B5"})}),
    "excel_get_table_columns": ({"workbook_id": "wb1", "table": "Sales"}, {("GET", f"{TABLE}/columns"): FakeResponse({"value": [{"name": "Name", "index": 0}]})}),
    "excel_get_table_rows": ({"workbook_id": "wb1", "table": "Sales"},
                             {("GET", f"{TABLE}/columns"): FakeResponse({"value": [{"name": "Name", "index": 0}]}),
                              ("GET", f"{TABLE}/rows"): FakeResponse({"value": [{"index": 0, "values": [["Kim"]]}]})}),
    "excel_append_table_rows": ({"workbook_id": "wb1", "table": "Sales", "rows": '[{"Name": "Lee"}]'},
                                {("GET", f"{TABLE}/columns"): FakeResponse({"value": [{"name": "Name", "index": 0}]}),
                                 ("POST", f"{TABLE}/rows"): FakeResponse({})}),
    "excel_lookup_table": ({"workbook_id": "wb1", "table": "Sales", "column": "Name", "value": "Kim"},
                           {("GET", f"{TABLE}/columns"): FakeResponse({"value": [{"name": "Name", "index": 0}]}),
                            ("GET", f"{TABLE}/rows"): FakeResponse({"value": [{"index": 0, "values": [["Kim"]]}]})}),
}
CASES.update({
    "excel_get_rows": ({"workbook_id": "wb1", "worksheet_name": "Sheet1"},
                       {("GET", USED): FakeResponse({"address": "Sheet1!A1:B2", "values": [["Name", "Score"], ["Kim", 90]]})}),
    "excel_update_rows": ({"workbook_id": "wb1", "worksheet_name": "Sheet1", "key_column": "Name", "rows": '[{"Name": "Kim", "Score": 95}]'},
                          {("GET", USED): FakeResponse({"address": "Sheet1!A1:B2", "values": [["Name", "Score"], ["Kim", 90]]}),
                           ("PATCH", f"{WB}/worksheets/Sheet1/range(address=%27A2%3AB2%27)"): FakeResponse({})}),
})


def schema(name):
    return yaml.safe_load((ROOT / "tools" / f"{name}.yaml").read_text(encoding="utf-8"))["output_schema"]["properties"]


def test_every_tool_listed_in_the_provider_is_covered():
    tools = yaml.safe_load((ROOT / "provider" / "microsoft_excel365.yaml").read_text(encoding="utf-8"))["tools"]
    assert {Path(t).stem for t in tools} - {"excel_sign_out"} == set(CASES)


@pytest.mark.parametrize("name", sorted(CASES))
def test_success_emits_every_declared_variable_with_its_type(name, monkeypatch):
    params, routes = CASES[name]
    _, out, _ = run(name, params, routes, monkeypatch)
    declared = schema(name)
    assert set(out) == set(declared)
    for var, spec in declared.items():
        assert isinstance(out[var], PY_TYPES[spec["type"]]), (name, var, out[var])
    assert out["success"] is True and out["error"] == ""


@pytest.mark.parametrize("name", sorted(CASES))
def test_graph_error_still_emits_every_variable(name, monkeypatch):
    params, _ = CASES[name]
    _, out, _ = run(name, params, {}, monkeypatch)
    assert set(out) == set(schema(name)) and out["success"] is False and out["error"]


def test_no_tool_hardcodes_the_global_graph_host():
    for path in (ROOT / "tools").glob("*.py"):
        if path.name != "graph_client.py":
            assert "graph.microsoft.com" not in path.read_text(encoding="utf-8"), path.name


# ── behaviour of the new tools ────────────────────────────────────────


def test_append_writes_the_header_on_an_empty_sheet(monkeypatch):
    graph, out, _ = run("excel_append_rows", {"workbook_id": "wb1", "worksheet_name": "Sheet1", "rows": [{"Name": "Kim", "Score": 90}, {"Name": "Lee"}]}, {
        ("GET", USED): FakeResponse({"address": "Sheet1!A1", "values": [[""]]}),
        ("PATCH", f"{WB}/worksheets/Sheet1/range(address=%27A1%3AB3%27)"): FakeResponse({"address": "Sheet1!A1:B3"}),
    }, monkeypatch)
    assert graph.calls[-1].json == {"values": [["Name", "Score"], ["Kim", 90], ["Lee", ""]]}
    assert out["rows_appended"] == 3


def test_append_below_data_that_does_not_start_at_a1(monkeypatch):
    graph, out, _ = run("excel_append_rows", {"workbook_id": "wb1", "worksheet_name": "Sheet1", "rows": '[["Lee", 70]]'}, {
        ("GET", USED): FakeResponse({"address": "Sheet1!C5:D6", "values": [["Name", "Score"], ["Kim", 90]]}),
        ("PATCH", f"{WB}/worksheets/Sheet1/range(address=%27C7%3AD7%27)"): FakeResponse({"address": "Sheet1!C7:D7"}),
    }, monkeypatch)
    assert out["success"] is True and graph.calls[-1].json == {"values": [["Lee", 70]]}


def test_append_rejects_keys_that_are_not_headers(monkeypatch):
    _, out, texts = run("excel_append_rows", {"workbook_id": "wb1", "worksheet_name": "Sheet1", "rows": '[{"Nmae": "x"}]'}, {
        ("GET", USED): FakeResponse({"address": "Sheet1!A1:B1", "values": [["Name", "Score"]]}),
    }, monkeypatch)
    assert out["success"] is False and "Nmae" in texts[0]


def test_upsert_updates_matches_keeps_other_cells_and_appends_the_rest(monkeypatch):
    patched = {}

    def record(call):
        patched[call.url.rsplit("range(address=", 1)[1]] = call.json["values"]
        return FakeResponse({})

    graph, out, _ = run("excel_upsert_rows", {"workbook_id": "wb1", "worksheet_name": "Sheet1", "key_column": "ID",
                                              "rows": [{"ID": 2, "Status": "Done"}, {"ID": "9", "Status": "New", "Owner": "Lee"}]}, {
        ("GET", USED): FakeResponse({"address": "Sheet1!A1:C3", "values": [["ID", "Status", "Owner"], [1, "Open", "Kim"], [2, "Open", "Park"]]}),
        ("PATCH", f"{WB}/worksheets/Sheet1/range(address=%27A3%3AC3%27)"): record,
        ("PATCH", f"{WB}/worksheets/Sheet1/range(address=%27A4%3AC4%27)"): record,
    }, monkeypatch)
    assert patched["%27A3%3AC3%27)"] == [[2, "Done", "Park"]]  # Owner untouched
    assert patched["%27A4%3AC4%27)"] == [["9", "New", "Lee"]]
    assert out["rows_updated"] == 1 and out["rows_appended"] == 1


def test_upsert_needs_the_key_column(monkeypatch):
    _, out, texts = run("excel_upsert_rows", {"workbook_id": "wb1", "worksheet_name": "Sheet1", "key_column": "Email", "rows": '[{"Email": "a@x"}]'}, {
        ("GET", USED): FakeResponse({"address": "Sheet1!A1:B1", "values": [["ID", "Status"]]}),
    }, monkeypatch)
    assert out["success"] is False and "not a column header" in texts[0]


def test_table_rows_lookup_and_append(monkeypatch):
    routes = {
        ("GET", f"{TABLE}/columns"): FakeResponse({"value": [{"name": "Score", "index": 1}, {"name": "Name", "index": 0}]}),
        ("GET", f"{TABLE}/rows"): FakeResponse({"value": [{"values": [["Kim", 90]]}, {"values": [["Lee", 42]]}]}),
        ("POST", f"{TABLE}/rows"): FakeResponse({}),
    }
    _, out, _ = run("excel_get_table_rows", {"workbook_id": "wb1", "table": "Sales"}, routes, monkeypatch)
    assert out["rows"] == [{"Name": "Kim", "Score": 90}, {"Name": "Lee", "Score": 42}]
    _, out, _ = run("excel_lookup_table", {"workbook_id": "wb1", "table": "Sales", "column": "Score", "value": "42"}, routes, monkeypatch)
    assert out["rows"] == [{"Name": "Lee", "Score": 42}]
    graph, out, _ = run("excel_append_table_rows", {"workbook_id": "wb1", "table": "Sales", "rows": '[{"Score": 1, "Name": "Choi"}]'}, routes, monkeypatch)
    assert graph.calls[-1].json == {"index": None, "values": [["Choi", 1]]}


def test_add_table_quotes_the_sheet_and_names_it(monkeypatch):
    graph, out, _ = run("excel_add_table", {"workbook_id": "wb1", "worksheet_name": "Q3's data", "range": "A1:C9", "table_name": "Sales"}, {
        ("POST", f"{WB}/tables/add"): FakeResponse({"id": "t9", "name": "Table1"}),
        ("PATCH", f"{WB}/tables/t9"): FakeResponse({"id": "t9", "name": "Sales"}),
    }, monkeypatch)
    assert graph.calls[0].json == {"address": "'Q3''s data'!A1:C9", "hasHeaders": True}
    assert out["name"] == "Sales"


def test_search_reports_cells_relative_to_the_range_start(monkeypatch):
    _, out, _ = run("search_worksheet_data", {"workbook_id": "wb1", "worksheet_name": "S", "search_value": "x", "range": "C5:D6"}, {
        ("GET", f"{WB}/worksheets/S/range(address=%27C5%3AD6%27)"): FakeResponse({"address": "S!C5:D6", "values": [["a", "b"], ["c", "X"]]}),
    }, monkeypatch)
    assert out["matches"] == [{"cell": "D6", "value": "X", "row": 6, "column": "D"}]


# ── provider ──────────────────────────────────────────────────────────


def test_oauth_tenant_and_cloud():
    url = Excel365Provider()._oauth_get_authorization_url("https://dify/cb", {"client_id": "c", "tenant_id": "contoso.onmicrosoft.com", "cloud": "china"})
    parsed = urlparse(url)
    assert parsed.netloc == "login.partner.microsoftonline.cn" and parsed.path.startswith("/contoso.onmicrosoft.com/")
    assert "https://microsoftgraph.chinacloudapi.cn/Files.ReadWrite" in parse_qs(parsed.query)["scope"][0]
    # Unset: the behaviour from before the settings existed.
    assert urlparse(Excel365Provider()._oauth_get_authorization_url("https://dify/cb", {"client_id": "c"})).path.startswith("/common/")


PER_USER = dict(SP, auth_mode="per_user", redirect_uri="https://dify.example.com/e/hook/excel/callback")


@pytest.mark.parametrize("redirect_uri, message", [
    ("", "Callback URL"), ("http://localhost/e/h/excel/callback", "localhost"), ("https://d/e/h/onedrive/callback", "/excel/callback"),
])
def test_per_user_validation_checks_the_callback_url(redirect_uri, message):
    with pytest.raises(ToolProviderCredentialValidationError, match=message):
        Excel365Provider()._validate_credentials(dict(PER_USER, redirect_uri=redirect_uri))


def test_per_user_validation_proves_the_secret(monkeypatch):
    graph_module._token_cache.clear()
    calls = []
    monkeypatch.setattr(graph_module.requests, "post", lambda url, data=None, timeout=None: calls.append(data) or FakeResponse({"access_token": "a", "expires_in": 3599}))
    Excel365Provider()._validate_credentials(dict(PER_USER))
    assert calls[0]["grant_type"] == "client_credentials"
    from tools.user_auth import DELEGATED_SCOPE
    assert set(DELEGATED_SCOPE.split()) == set(Excel365Provider._SCOPES.split())


def test_service_principal_validation_opens_the_default_drive(monkeypatch):
    graph_module._token_cache.clear()
    monkeypatch.setattr(graph_module.requests, "post", lambda *a, **k: FakeResponse({"access_token": "app", "expires_in": 3599}))
    import provider.microsoft_excel365 as provider_module
    monkeypatch.setattr(provider_module.requests, "get", lambda *a, **k: FakeResponse({"error": {}}, 403))
    with pytest.raises(ToolProviderCredentialValidationError, match="Files.ReadWrite.All"):
        Excel365Provider()._validate_credentials(dict(SP, drive_user="alice@contoso.com"))
    Excel365Provider()._validate_credentials(dict(SP))  # no default drive: sign-in only


@pytest.mark.parametrize("address, expected", [
    ("Sheet1!C5:D6", (2, 5)), ("C5", (2, 5)), ("'Q3''s 2026'!$AA$10:AB12", (26, 10)), ("Data2024!A1", (0, 1)), ("", (0, 1)),
])
def test_top_left_ignores_the_sheet_name(address, expected):
    assert graph_module.top_left(address) == expected


# ── row options: Get Rows, Update, Update All Matches, Return All Matches ──

SHEET = {"address": "Sheet1!A1:C5", "values": [["Title", "", ""], ["ID", "Status", "Owner"], [1, "Open", "Kim"], ["", "", ""], [1, "Open", "Lee"]]}


def test_get_rows_uses_the_header_row_and_skips_blank_rows(monkeypatch):
    _, out, _ = run("excel_get_rows", {"workbook_id": "wb1", "worksheet_name": "Sheet1", "header_row": 1}, {("GET", USED): FakeResponse(SHEET)}, monkeypatch)
    assert out["columns"] == ["ID", "Status", "Owner"]
    assert out["rows"] == [{"ID": 1, "Status": "Open", "Owner": "Kim"}, {"ID": 1, "Status": "Open", "Owner": "Lee"}]
    _, out, _ = run("excel_get_rows", {"workbook_id": "wb1", "worksheet_name": "Sheet1", "header_row": 1, "limit": 1}, {("GET", USED): FakeResponse(SHEET)}, monkeypatch)
    assert out["count"] == 1 and out["has_more"] is True


def test_get_rows_reads_a_given_range_and_checks_the_row_numbers(monkeypatch):
    graph, out, _ = run("excel_get_rows", {"workbook_id": "wb1", "worksheet_name": "Sheet1", "range": "B2:C3"}, {
        ("GET", f"{WB}/worksheets/Sheet1/range(address=%27B2%3AC3%27)"): FakeResponse({"address": "Sheet1!B2:C3", "values": [["Status", "Owner"], ["Open", "Kim"]]}),
    }, monkeypatch)
    assert out["rows"] == [{"Status": "Open", "Owner": "Kim"}]
    _, out, texts = run("excel_get_rows", {"workbook_id": "wb1", "worksheet_name": "Sheet1", "header_row": 2, "first_data_row": 1}, {}, monkeypatch)
    assert out["success"] is False and "after header_row" in texts[0]


DUPES = {"address": "Sheet1!A1:C4", "values": [["ID", "Status", "Owner"], [1, "Open", "Kim"], [2, "Open", "Park"], [1, "Open", "Lee"]]}


def patches(graph):
    return {c.url.rsplit("address=", 1)[1]: c.json["values"] for c in graph.calls if c.method == "PATCH"}


def routes_for(sheet):
    ok = lambda call: FakeResponse({})  # noqa: E731
    routes = {("GET", USED): FakeResponse(sheet)}
    for row in range(2, 8):
        routes[("PATCH", f"{WB}/worksheets/Sheet1/range(address=%27A{row}%3AC{row}%27)")] = ok
    return routes


def test_update_rows_changes_matches_only_and_reports_the_rest(monkeypatch):
    graph, out, texts = run("excel_update_rows", {"workbook_id": "wb1", "worksheet_name": "Sheet1", "key_column": "ID",
                                                   "rows": [{"ID": 1, "Status": "Done"}, {"ID": 7, "Status": "New"}]}, routes_for(DUPES), monkeypatch)
    assert patches(graph) == {"%27A2%3AC2%27)": [[1, "Done", "Kim"]]}  # first match only, Owner kept
    assert out["rows_updated"] == 1 and out["not_found"] == ["7"] and "nothing was added" in texts[0]


def test_update_all_matches(monkeypatch):
    graph, out, _ = run("excel_update_rows", {"workbook_id": "wb1", "worksheet_name": "Sheet1", "key_column": "ID", "update_all": True,
                                               "rows": '[{"ID": 1, "Status": "Done"}]'}, routes_for(DUPES), monkeypatch)
    assert patches(graph) == {"%27A2%3AC2%27)": [[1, "Done", "Kim"]], "%27A4%3AC4%27)": [[1, "Done", "Lee"]]}
    assert out["rows_updated"] == 2


def test_upsert_update_all_matches_and_append(monkeypatch):
    graph, out, _ = run("excel_upsert_rows", {"workbook_id": "wb1", "worksheet_name": "Sheet1", "key_column": "ID", "update_all": True,
                                               "rows": '[{"ID": 1, "Owner": "Choi"}, {"ID": 9, "Status": "New"}]'}, routes_for(DUPES), monkeypatch)
    assert patches(graph) == {"%27A2%3AC2%27)": [[1, "Open", "Choi"]], "%27A4%3AC4%27)": [[1, "Open", "Choi"]], "%27A5%3AC5%27)": [[9, "New", ""]]}
    assert out["rows_updated"] == 2 and out["rows_appended"] == 1


def test_lookup_can_return_only_the_first_match(monkeypatch):
    routes = {
        ("GET", f"{TABLE}/columns"): FakeResponse({"value": [{"name": "Name", "index": 0}]}),
        ("GET", f"{TABLE}/rows"): FakeResponse({"value": [{"values": [["Kim"]]}, {"values": [["Kim"]]}]}),
    }
    _, out, _ = run("excel_lookup_table", {"workbook_id": "wb1", "table": "Sales", "column": "Name", "value": "Kim"}, routes, monkeypatch)
    assert out["count"] == 2
    _, out, _ = run("excel_lookup_table", {"workbook_id": "wb1", "table": "Sales", "column": "Name", "value": "Kim", "return_all_matches": False}, routes, monkeypatch)
    assert out["count"] == 1

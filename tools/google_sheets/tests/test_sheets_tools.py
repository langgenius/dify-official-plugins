import importlib
import inspect
from pathlib import Path

import pytest
import yaml
from dify_plugin import Tool
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from provider.google_sheets import GoogleSheetsProvider
from tests.fakes import API, OAUTH, PER_USER, FakeHttp, make_tool, run
from tools.google_sheets_append_rows import GoogleSheetsAppendRowsTool
from tools.google_sheets_create_spreadsheet import GoogleSheetsCreateSpreadsheetTool
from tools.google_sheets_delete_rows import GoogleSheetsDeleteRowsTool
from tools.google_sheets_find_spreadsheets import GoogleSheetsFindSpreadsheetsTool
from tools.google_sheets_read_range import GoogleSheetsReadRangeTool
from tools.google_sheets_read_rows import GoogleSheetsReadRowsTool
from tools.google_sheets_sign_out import SignOutTool
from tools.google_sheets_update_rows import GoogleSheetsUpdateRowsTool
from tools.google_sheets_upsert_rows import GoogleSheetsUpsertRowsTool
from tools.google_sheets_write_range import GoogleSheetsWriteRangeTool
from tools.sheets_ops import column_letter, quote_sheet

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = yaml.safe_load((ROOT / "provider" / "google_sheets.yaml").read_text(encoding="utf-8"))
META = {"spreadsheetId": "s1", "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/s1/edit", "properties": {"title": "Scores"},
        "sheets": [{"properties": {"sheetId": 0, "title": "Sheet1", "gridProperties": {"rowCount": 1000, "columnCount": 26}}},
                   {"properties": {"sheetId": 7, "title": "Q2 'final'", "gridProperties": {"rowCount": 10, "columnCount": 5}}}]}
VALUES = {"values": [["Name", "Score", "Team"], ["Alice", "90", "A"], [], ["Bob", "85", "B"], ["alice", "70", "B"]]}


@pytest.fixture
def http(monkeypatch):
    http = FakeHttp().install(monkeypatch)
    # The values route first: the spreadsheet URL is a prefix of every values URL.
    http.on("GET", "/values/", VALUES)
    http.on("GET", f"{API}/s1", META)
    return http


def test_helpers():
    assert [column_letter(i) for i in (0, 25, 26, 701, 702)] == ["A", "Z", "AA", "ZZ", "AAA"]
    assert quote_sheet("Q2 'final'") == "'Q2 ''final'''"


def test_read_rows_skips_blank_rows_and_filters(http):
    result = run(make_tool(GoogleSheetsReadRowsTool, OAUTH), {"spreadsheet_id": "https://docs.google.com/spreadsheets/d/s1/edit#gid=0"})
    assert result.vars["count"] == 3 and result.vars["headers"] == ["Name", "Score", "Team"]
    assert result.vars["rows"][1] == {"Name": "Bob", "Score": "85", "Team": "B", "row_number": 4}
    assert http.calls[1].url == f"{API}/s1/values/%27Sheet1%27"
    filtered = run(make_tool(GoogleSheetsReadRowsTool, OAUTH), {"spreadsheet_id": "s1", "filter_column": "name", "filter_value": "ALICE"})
    assert [r["row_number"] for r in filtered.vars["rows"]] == [2, 5]


def test_unknown_sheet_and_column(http):
    assert "No sheet named 'Nope'" in run(make_tool(GoogleSheetsReadRowsTool, OAUTH), {"spreadsheet_id": "s1", "sheet": "Nope"}).vars["error"]
    bad = run(make_tool(GoogleSheetsReadRowsTool, OAUTH), {"spreadsheet_id": "s1", "filter_column": "Age", "filter_value": "1"})
    assert "No column 'Age'" in bad.vars["error"]


def test_append_rows_maps_keys_to_header_order(http):
    http.on("POST", ":append", {"updates": {"updatedRange": "Sheet1!A6:C6"}})
    result = run(make_tool(GoogleSheetsAppendRowsTool, OAUTH), {"spreadsheet_id": "s1", "rows": '[{"team": "C", "Name": "Carol", "Score": 88}]'})
    call = http.calls[-1]
    assert call.json == {"values": [["Carol", 88, "C"]]} and call.params["valueInputOption"] == "USER_ENTERED"
    assert result.vars == {"appended": 1, "range": "Sheet1!A6:C6", "success": True, "error": ""}


def test_append_rejects_or_adds_unknown_columns(http):
    http.on("POST", ":append", {"updates": {"updatedRange": "x"}})
    http.on("PUT", "/values/", {})
    bad = run(make_tool(GoogleSheetsAppendRowsTool, OAUTH), {"spreadsheet_id": "s1", "rows": '[{"Name": "D", "Age": 3}]'})
    assert "Unknown column(s) ['Age']" in bad.vars["error"]
    run(make_tool(GoogleSheetsAppendRowsTool, OAUTH), {"spreadsheet_id": "s1", "rows": '[{"Name": "D", "Age": 3}]', "add_missing_columns": True})
    header_put = [c for c in http.calls if c.method == "PUT"][0]
    assert header_put.json == {"values": [["Name", "Score", "Team", "Age"]]}
    assert http.calls[-1].json == {"values": [["D", "", "", 3]]}


def test_update_rows_by_key(http):
    http.on("POST", "values:batchUpdate", {})
    result = run(make_tool(GoogleSheetsUpdateRowsTool, OAUTH),
                 {"spreadsheet_id": "s1", "key_column": "name", "rows": '[{"Name": "alice", "Score": 95}, {"Name": "Zed", "Score": 1}]'})
    data = http.calls[-1].json["data"]
    # Only the first match (row 2), only the given columns; Zed is reported, not appended.
    assert data == [{"range": "'Sheet1'!A2", "values": [["alice"]]}, {"range": "'Sheet1'!B2", "values": [[95]]}]
    assert result.vars == {"updated": 1, "appended": 0, "not_found": 1, "success": True, "error": ""}
    run(make_tool(GoogleSheetsUpdateRowsTool, OAUTH),
        {"spreadsheet_id": "s1", "key_column": "Name", "rows": '[{"Name": "Alice", "Team": "Z"}]', "update_all_matches": True})
    assert [d["range"] for d in http.calls[-1].json["data"] if "C" in d["range"]] == ["'Sheet1'!C2", "'Sheet1'!C5"]


def test_upsert_appends_the_unmatched(http):
    http.on("POST", "values:batchUpdate", {})
    http.on("POST", ":append", {"updates": {"updatedRange": "Sheet1!A6:C6"}})
    result = run(make_tool(GoogleSheetsUpsertRowsTool, OAUTH),
                 {"spreadsheet_id": "s1", "key_column": "Name", "rows": '[{"Name": "Bob", "Score": 99}, {"Name": "Zed", "Score": 1}]'})
    assert result.vars["updated"] == 1 and result.vars["appended"] == 1
    assert http.calls[-1].json == {"values": [["Zed", 1, ""]]}


def test_update_needs_key_values_and_valid_json(http):
    assert "needs a value for the key column" in run(make_tool(GoogleSheetsUpdateRowsTool, OAUTH),
                                                     {"spreadsheet_id": "s1", "key_column": "Name", "rows": '[{"Score": 1}]'}).vars["error"]
    assert "rows must be" in run(make_tool(GoogleSheetsUpdateRowsTool, OAUTH),
                                 {"spreadsheet_id": "s1", "key_column": "Name", "rows": "not json"}).vars["error"]


def test_delete_rows_bottom_up(http):
    http.on("POST", f"{API}/s1:batchUpdate", {})
    result = run(make_tool(GoogleSheetsDeleteRowsTool, OAUTH), {"spreadsheet_id": "s1", "filter_column": "Name", "filter_value": "alice"})
    starts = [r["deleteDimension"]["range"]["startIndex"] for r in http.calls[-1].json["requests"]]
    assert starts == [4, 1] and result.vars["deleted"] == 2
    assert "below the header" in run(make_tool(GoogleSheetsDeleteRowsTool, OAUTH), {"spreadsheet_id": "s1", "row_numbers": "1"}).vars["error"]


def test_ranges(http):
    http.on("PUT", "/values/", {"updatedCells": 4, "updatedRange": "'Q2 ''final'''!B2:C3"})
    result = run(make_tool(GoogleSheetsWriteRangeTool, OAUTH), {"spreadsheet_id": "s1", "sheet": "q2 'final'", "range": "B2", "values": '[["a", 1], ["b", "=A1"]]'})
    assert http.calls[-1].url == f"{API}/s1/values/%27Q2%20%27%27final%27%27%27%21B2" and result.vars["updated_cells"] == 4
    run(make_tool(GoogleSheetsReadRangeTool, OAUTH), {"spreadsheet_id": "s1", "range": "Sheet1!A1:B2", "value_render": "FORMULA"})
    assert http.calls[-1].params == {"valueRenderOption": "FORMULA"}
    assert "JSON array of rows" in run(make_tool(GoogleSheetsWriteRangeTool, OAUTH), {"spreadsheet_id": "s1", "range": "A1", "values": "[1,2]"}).vars["error"]


def test_create_and_find(http):
    http.on("POST", API, {"spreadsheetId": "s9", "spreadsheetUrl": "u", "sheets": [{"properties": {"sheetId": 0, "title": "Data"}}]})
    http.on("PUT", "/s9/values/", {})
    run(make_tool(GoogleSheetsCreateSpreadsheetTool, OAUTH), {"title": "New", "sheets": "Data, Notes", "headers": "Name, Score"})
    assert http.calls[0].json["sheets"] == [{"properties": {"title": "Data"}}, {"properties": {"title": "Notes"}}]
    assert http.calls[1].json == {"values": [["Name", "Score"]]}
    http.on("GET", "drive/v3/files", {"files": [{"id": "s1", "name": "Scores"}]})
    found = run(make_tool(GoogleSheetsFindSpreadsheetsTool, OAUTH), {"name": "O'Brien"})
    assert "name contains 'O\\'Brien'" in http.calls[-1].params["q"] and found.vars["count"] == 1


def test_per_user_and_sign_out(http):
    assert "/google_sheets/callback?start=" in run(make_tool(GoogleSheetsReadRowsTool, PER_USER), {"spreadsheet_id": "s1"}).texts[0]
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
    assert spec["identity"]["name"].startswith("google_sheets_")
    result = run(make_tool(tool_class(spec), {}))
    assert set(result.vars) == set(spec["output_schema"]["properties"]) and result.vars["success"] is False


def test_manifest_and_provider(http):
    manifest = yaml.safe_load((ROOT / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["name"] == "google_sheets" and manifest["plugins"]["endpoints"] == ["group/google_sheets_signin.yaml"]
    provider = GoogleSheetsProvider.__new__(GoogleSheetsProvider)
    provider._validate_credentials(PER_USER)
    with pytest.raises(ToolProviderCredentialValidationError, match="/google_sheets/callback"):
        provider._validate_credentials({**PER_USER, "redirect_uri": "https://d.example.com/e/x/gmail/callback"})
    assert "auth%2Fspreadsheets" in provider._oauth_get_authorization_url("https://dify/cb", {"client_id": "cid"})

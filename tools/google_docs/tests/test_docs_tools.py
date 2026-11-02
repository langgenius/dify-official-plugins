import importlib
import inspect
from pathlib import Path

import pytest
import yaml
from dify_plugin import Tool
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from provider.google_docs import GoogleDocsProvider
from tests.fakes import API, OAUTH, PER_USER, FakeHttp, make_tool, run
from tools.docs_ops import body_end, parse_markdown, to_markdown, write_requests
from tools.google_docs_append_content import GoogleDocsAppendContentTool
from tools.google_docs_create_document import GoogleDocsCreateDocumentTool
from tools.google_docs_find_documents import GoogleDocsFindDocumentsTool
from tools.google_docs_get_document import GoogleDocsGetDocumentTool
from tools.google_docs_insert_table import GoogleDocsInsertTableTool
from tools.google_docs_replace_text import GoogleDocsReplaceTextTool
from tools.google_docs_sign_out import SignOutTool

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = yaml.safe_load((ROOT / "provider" / "google_docs.yaml").read_text(encoding="utf-8"))


def para(text, style="NORMAL_TEXT", start=1, bullet=None, **text_style):
    p = {"startIndex": start, "endIndex": start + len(text) + 1,
         "paragraph": {"elements": [{"textRun": {"content": text + "\n", "textStyle": text_style}}], "paragraphStyle": {"namedStyleType": style}}}
    if bullet is not None:
        p["paragraph"]["bullet"] = {"listId": bullet, "nestingLevel": 0}
    return p


DOC = {"title": "Plan", "lists": {"num": {"listProperties": {"nestingLevels": [{"glyphType": "DECIMAL"}]}}, "dot": {"listProperties": {"nestingLevels": [{"glyphSymbol": "●"}]}}},
       "body": {"content": [{"sectionBreak": {}, "endIndex": 1}, para("Goals", "HEADING_1"), para("Ship it", bullet="dot", start=7),
                            para("Step one", bullet="num", start=15), para("Read docs", start=24, link={"url": "https://x.y"}),
                            {"startIndex": 34, "endIndex": 60, "table": {"tableRows": [
                                {"tableCells": [{"content": [para("Name")]}, {"content": [para("Score")]}]},
                                {"tableCells": [{"content": [para("Kim")]}, {"content": [para("90")]}]}]}},
                            para("", start=60)]}}


@pytest.fixture
def http(monkeypatch):
    return FakeHttp().install(monkeypatch)


def test_parse_markdown():
    paras = parse_markdown("# Title\nSome **bold** and *it* and [link](https://a.b)\n- one\n- two\n1. first\n\n")
    assert [(p.text, p.style, p.list_kind) for p in paras] == [
        ("Title", "HEADING_1", None), ("Some bold and it and link", "NORMAL_TEXT", None),
        ("one", "NORMAL_TEXT", "bullet"), ("two", "NORMAL_TEXT", "bullet"), ("first", "NORMAL_TEXT", "numbered")]
    assert [(s, e, f) for s, e, _, f in paras[1].spans] == [(5, 9, "bold"), (14, 16, "italic"), (21, 25, "link")]


def test_write_requests_indexes_at_the_end_of_a_document():
    reqs = write_requests(parse_markdown("# H\n- a\n- b\nx **y**"), 10, True, False)
    assert reqs[0] == {"insertText": {"location": {"index": 10}, "text": "\nH\na\nb\nx y"}}
    assert reqs[1]["updateParagraphStyle"]["range"] == {"startIndex": 11, "endIndex": 20}
    heading = [r for r in reqs if r.get("updateParagraphStyle", {}).get("paragraphStyle", {}).get("namedStyleType") == "HEADING_1"]
    assert heading[0]["updateParagraphStyle"]["range"] == {"startIndex": 11, "endIndex": 12}
    bold = [r for r in reqs if "updateTextStyle" in r][0]["updateTextStyle"]["range"]
    assert bold == {"startIndex": 19, "endIndex": 20}
    bullets = [r for r in reqs if "createParagraphBullets" in r]
    assert len(bullets) == 1 and bullets[0]["createParagraphBullets"]["range"] == {"startIndex": 13, "endIndex": 16}


def test_write_requests_at_the_start_keeps_a_newline():
    reqs = write_requests(parse_markdown("Intro"), 1, False, True)
    assert reqs[0]["insertText"] == {"location": {"index": 1}, "text": "Intro\n"}


def test_inline_styles_use_utf16_offsets():
    (paragraph,) = parse_markdown("😀 **B😀** *I😀* [L😀](https://a.b)")
    assert [(s, e, field) for s, e, _, field in paragraph.spans] == [
        (3, 6, "bold"), (7, 10, "italic"), (11, 14, "link")]


def test_paragraph_and_list_ranges_use_utf16_offsets():
    reqs = write_requests(parse_markdown("# 😀\n- 😀\n- x\n😀 **y**"), 10, True, False)
    assert reqs[1]["updateParagraphStyle"]["range"] == {"startIndex": 11, "endIndex": 23}
    heading = next(r["updateParagraphStyle"] for r in reqs
                   if r.get("updateParagraphStyle", {}).get("paragraphStyle", {}).get("namedStyleType") == "HEADING_1")
    assert heading["range"] == {"startIndex": 11, "endIndex": 13}
    bold = next(r["updateTextStyle"] for r in reqs if "updateTextStyle" in r)
    assert bold["range"] == {"startIndex": 22, "endIndex": 23}
    bullets = next(r["createParagraphBullets"] for r in reqs if "createParagraphBullets" in r)
    assert bullets["range"] == {"startIndex": 14, "endIndex": 18}


def test_table_header_style_uses_utf16_offsets(http):
    table = {"table": {"tableRows": [{"tableCells": [{"content": [{"startIndex": 5}]}]}]}}
    http.on("POST", ":batchUpdate", {})
    http.on("GET", f"{API}/d1", {"body": {"content": [table]}})
    result = run(make_tool(GoogleDocsInsertTableTool, OAUTH), {"document_id": "d1", "values": '[["😀"]]'})
    assert result.vars["success"]
    bold = next(r["updateTextStyle"] for r in http.calls[-1].json["requests"] if "updateTextStyle" in r)
    assert bold["range"] == {"startIndex": 5, "endIndex": 7}


def test_body_end():
    assert body_end(DOC) == (60, False)
    assert body_end({"body": {"content": [{"endIndex": 1}, para("Hi")]}}) == (3, True)


def test_to_markdown():
    text, headings = to_markdown(DOC)
    assert text.splitlines() == ["# Goals", "- Ship it", "1. Step one", "[Read docs](https://x.y)", "| Name | Score |", "| --- | --- |", "| Kim | 90 |"]
    assert headings == ["Goals"]


def test_get_document_accepts_a_url(http):
    http.on("GET", f"{API}/d1", DOC)
    result = run(make_tool(GoogleDocsGetDocumentTool, OAUTH), {"document_id": "https://docs.google.com/document/d/d1/edit"})
    assert result.vars["title"] == "Plan" and result.vars["text"].startswith("# Goals") and http.calls[0].url == f"{API}/d1"


def test_create_with_content(http):
    http.on("POST", f"{API}/d9:batchUpdate", {})
    http.on("POST", API, {"documentId": "d9"})
    result = run(make_tool(GoogleDocsCreateDocumentTool, OAUTH), {"title": "Notes", "content": "Hello"})
    assert http.calls[0].json == {"title": "Notes"}
    assert http.calls[1].json["requests"][0] == {"insertText": {"location": {"index": 1}, "text": "Hello"}}
    assert result.vars["url"] == "https://docs.google.com/document/d/d9/edit"


def test_append_at_the_end_with_page_break(http):
    http.on("GET", f"{API}/d1", {"body": {"content": [{"endIndex": 1}, para("Hi")]}})
    http.on("POST", ":batchUpdate", {})
    run(make_tool(GoogleDocsAppendContentTool, OAUTH), {"document_id": "d1", "content": "More", "page_break_before": True})
    reqs = http.calls[-1].json["requests"]
    assert reqs[0] == {"insertText": {"location": {"index": 3}, "text": "\nMore"}}
    assert reqs[-1] == {"insertPageBreak": {"location": {"index": 3}}}


def test_replace_text_pairs(http):
    http.on("POST", ":batchUpdate", {"replies": [{"replaceAllText": {"occurrencesChanged": 2}}, {"replaceAllText": {}}]})
    result = run(make_tool(GoogleDocsReplaceTextTool, OAUTH),
                 {"document_id": "d1", "replacements": '{"{{name}}": "Kim"}', "find": "old", "replace": "", "match_case": False})
    reqs = http.calls[0].json["requests"]
    assert reqs[0] == {"replaceAllText": {"containsText": {"text": "{{name}}", "matchCase": False}, "replaceText": "Kim"}}
    assert reqs[1]["replaceAllText"]["replaceText"] == "" and result.vars["replaced"] == 2
    assert "Give find" in run(make_tool(GoogleDocsReplaceTextTool, OAUTH), {"document_id": "d1"}).vars["error"]


def test_insert_table_fills_cells_bottom_up(http):
    table = {"table": {"tableRows": [{"tableCells": [{"content": [{"startIndex": 5}]}, {"content": [{"startIndex": 7}]}]},
                                     {"tableCells": [{"content": [{"startIndex": 10}]}, {"content": [{"startIndex": 12}]}]}]}}
    http.on("POST", ":batchUpdate", {})
    http.on("GET", f"{API}/d1", {"body": {"content": [{"endIndex": 1}, table, para("", start=14)]}})
    result = run(make_tool(GoogleDocsInsertTableTool, OAUTH), {"document_id": "d1", "values": '[["Name", "Score"], ["Kim", 90]]'})
    assert http.calls[0].json["requests"][0]["insertTable"] == {"rows": 2, "columns": 2, "endOfSegmentLocation": {"segmentId": ""}}
    inserts = [r["insertText"]["location"]["index"] for r in http.calls[-1].json["requests"] if "insertText" in r]
    assert inserts == [12, 10, 7, 5] and result.vars == {"rows": 2, "columns": 2, "success": True, "error": ""}
    assert "JSON array of rows" in run(make_tool(GoogleDocsInsertTableTool, OAUTH), {"document_id": "d1", "values": "[1]"}).vars["error"]


def test_find_documents(http):
    http.on("GET", "drive/v3/files", {"files": [{"id": "d1", "name": "Plan"}]})
    assert run(make_tool(GoogleDocsFindDocumentsTool, OAUTH), {"name": "Plan"}).vars["count"] == 1
    assert "application/vnd.google-apps.document" in http.calls[0].params["q"]


def test_per_user_and_sign_out(http):
    assert "/google_docs/callback?start=" in run(make_tool(GoogleDocsGetDocumentTool, PER_USER), {"document_id": "d1"}).texts[0]
    assert run(make_tool(SignOutTool, PER_USER)).vars == {"signed_out": False, "success": True, "error": ""}


def tool_class(spec):
    module = importlib.import_module(spec["extra"]["python"]["source"][:-3].replace("/", "."))
    classes = [c for _, c in inspect.getmembers(module, inspect.isclass) if issubclass(c, Tool) and c is not Tool]
    assert len(classes) == 1, classes
    return classes[0]


@pytest.mark.parametrize("tool_file", PROVIDER["tools"])
def test_every_tool_loads_and_emits_its_outputs(tool_file, http):
    spec = yaml.safe_load((ROOT / tool_file).read_text(encoding="utf-8"))
    assert spec["identity"]["name"].startswith("google_docs_")
    result = run(make_tool(tool_class(spec), {}))
    assert set(result.vars) == set(spec["output_schema"]["properties"]) and result.vars["success"] is False


def test_manifest_and_provider(http):
    manifest = yaml.safe_load((ROOT / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["name"] == "google_docs" and manifest["plugins"]["endpoints"] == ["group/google_docs_signin.yaml"]
    provider = GoogleDocsProvider.__new__(GoogleDocsProvider)
    provider._validate_credentials(PER_USER)
    with pytest.raises(ToolProviderCredentialValidationError, match="/google_docs/callback"):
        provider._validate_credentials({**PER_USER, "redirect_uri": "https://d.example.com/e/x/gmail/callback"})
    assert "auth%2Fdocuments" in provider._oauth_get_authorization_url("https://dify/cb", {"client_id": "cid"})

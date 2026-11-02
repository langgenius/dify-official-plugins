import base64
import email
import importlib
import inspect
from pathlib import Path

import pytest
import yaml
from dify_plugin import Tool
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from tests.fakes import API, OAUTH, PER_USER, FakeHttp, FakeResponse, make_tool, run
from tools.gmail_delete_label import GmailDeleteLabelTool
from tools.gmail_get_draft import GmailGetDraftTool
from tools.gmail_get_thread import GmailGetThreadTool
from tools.gmail_list_labels import GmailListLabelsTool
from tools.gmail_mark_read import GmailMarkReadTool
from tools.gmail_modify_labels import GmailModifyLabelsTool
from tools.gmail_reply import GmailReplyTool
from tools.gmail_sign_out import SignOutTool
from tools.gmail_trash_message import GmailTrashMessageTool
from tools.search_messages import SearchMessagesTool

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = yaml.safe_load((ROOT / "provider" / "dify-gmail.yaml").read_text(encoding="utf-8"))
LABELS = {"labels": [{"id": "INBOX", "name": "INBOX", "type": "system"}, {"id": "Label_7", "name": "Clients", "type": "user"},
                     {"id": "STARRED", "name": "STARRED", "type": "system"}]}


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


ORIGINAL = {"id": "m1", "threadId": "t1", "payload": {"headers": [
    {"name": "From", "value": "Bob <bob@example.com>"}, {"name": "To", "value": "me@gmail.com, carol@example.com"},
    {"name": "Cc", "value": "dave@example.com"}, {"name": "Subject", "value": "Quarterly report"},
    {"name": "Message-ID", "value": "<abc@mail.example.com>"}, {"name": "References", "value": "<prev@mail.example.com>"}]}}


@pytest.fixture
def http(monkeypatch):
    return FakeHttp().install(monkeypatch)


def sent_mime(call) -> email.message.Message:
    raw = call.json["raw"]
    return email.message_from_bytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))


def test_reply_keeps_the_thread(http):
    http.on("GET", "/messages/m1", ORIGINAL)
    http.on("GET", "/profile", {"emailAddress": "me@gmail.com"})
    http.on("POST", "/messages/send", {"id": "m2", "threadId": "t1"})
    result = run(make_tool(GmailReplyTool, OAUTH), {"message_id": "m1", "body": "Thanks!"})
    assert result.vars == {"message_id": "m2", "thread_id": "t1", "success": True, "error": ""}
    send = http.calls[-1]
    assert send.json["threadId"] == "t1"
    mime = sent_mime(send)
    assert mime["To"] == "bob@example.com" and mime["Cc"] is None
    assert mime["Subject"] == "Re: Quarterly report" and mime["In-Reply-To"] == "<abc@mail.example.com>"
    assert mime["References"] == "<prev@mail.example.com> <abc@mail.example.com>"
    assert http.calls[0].params["metadataHeaders"][0] == "From"


def test_reply_all_copies_others_but_not_me(http):
    http.on("GET", "/messages/m1", ORIGINAL)
    http.on("GET", "/profile", {"emailAddress": "Me@Gmail.com"})
    http.on("POST", "/messages/send", {"id": "m2", "threadId": "t1"})
    run(make_tool(GmailReplyTool, OAUTH), {"message_id": "m1", "body": "Hi all", "reply_all": True, "body_html": "<p>Hi all</p>"})
    mime = sent_mime(http.calls[-1])
    assert mime["To"] == "bob@example.com" and mime["Cc"] == "carol@example.com, dave@example.com"
    assert mime.is_multipart()


def test_reply_to_my_own_message_goes_to_its_recipients(http):
    mine = {**ORIGINAL, "payload": {"headers": [{"name": "From", "value": "me@gmail.com"}, {"name": "To", "value": "bob@example.com"},
                                                {"name": "Subject", "value": "Re: x"}]}}
    http.on("GET", "/messages/m1", mine)
    http.on("GET", "/profile", {"emailAddress": "me@gmail.com"})
    http.on("POST", "/messages/send", {"id": "m3", "threadId": "t1"})
    run(make_tool(GmailReplyTool, OAUTH), {"message_id": "m1", "body": "ping"})
    mime = sent_mime(http.calls[-1])
    assert mime["To"] == "bob@example.com" and mime["Subject"] == "Re: x"


def test_trash_and_restore(http):
    http.on("POST", "/messages/m1/trash", {"id": "m1"})
    http.on("POST", "/messages/m1/untrash", {"id": "m1"})
    assert "trash" in run(make_tool(GmailTrashMessageTool, OAUTH), {"message_id": "m1"}).texts[-1]
    assert "Restored" in run(make_tool(GmailTrashMessageTool, OAUTH), {"message_id": "m1", "restore": True}).texts[-1]


def test_mark_read_and_unread(http):
    http.on("POST", "/messages/m1/modify", {"id": "m1", "labelIds": ["INBOX"]})
    assert run(make_tool(GmailMarkReadTool, OAUTH), {"message_id": "m1"}).vars["unread"] is False
    assert http.calls[0].json == {"removeLabelIds": ["UNREAD"]}
    run(make_tool(GmailMarkReadTool, OAUTH), {"message_id": "m1", "read": False})
    assert http.calls[1].json == {"addLabelIds": ["UNREAD"]}


def test_modify_labels_by_name_system_and_create(http):
    http.on("GET", "/labels", LABELS)
    http.on("POST", f"{API}/labels", {"id": "Label_9", "name": "New"})
    http.on("POST", "/threads/t1/modify", {"id": "t1", "messages": [{"labelIds": ["Label_7", "STARRED"]}]})
    result = run(make_tool(GmailModifyLabelsTool, OAUTH),
                 {"thread_id": "t1", "add_labels": "clients, starred, New", "remove_labels": "INBOX", "create_missing": True})
    modify = http.calls[-1]
    assert modify.json == {"addLabelIds": ["Label_7", "STARRED", "Label_9"], "removeLabelIds": ["INBOX"]}
    assert result.vars["labels"] == ["Label_7", "STARRED"]


def test_modify_labels_unknown_label(http):
    http.on("GET", "/labels", LABELS)
    result = run(make_tool(GmailModifyLabelsTool, OAUTH), {"message_id": "m1", "add_labels": "Nope"})
    assert "No label named 'Nope'" in result.vars["error"]


def test_labels(http):
    http.on("GET", "/labels", LABELS)
    http.on("DELETE", "/labels/Label_7", FakeResponse(None, 204))
    listed = run(make_tool(GmailListLabelsTool, OAUTH))
    assert listed.vars["labels"][0]["name"] == "Clients" and "Your own: Clients" in listed.texts[-1]
    assert run(make_tool(GmailDeleteLabelTool, OAUTH), {"label": "Clients"}).vars["deleted"]
    assert "system label" in run(make_tool(GmailDeleteLabelTool, OAUTH), {"label": "INBOX"}).vars["error"]


def test_get_thread_reads_plain_and_html_bodies(http):
    http.on("GET", "/threads/t1", {"messages": [
        {"id": "m1", "threadId": "t1", "payload": {"headers": [{"name": "From", "value": "Bob"}, {"name": "Subject", "value": "Hi"}],
                                                   "mimeType": "multipart/alternative", "parts": [
                                                       {"mimeType": "text/plain", "body": {"data": b64("Plain hello")}},
                                                       {"mimeType": "text/html", "body": {"data": b64("<p>ignored</p>")}}]}},
        {"id": "m2", "threadId": "t1", "payload": {"headers": [{"name": "From", "value": "Me"}], "mimeType": "text/html",
                                                   "body": {"data": b64("<p>Only&nbsp;HTML<br>line 2</p>")}}}]})
    result = run(make_tool(GmailGetThreadTool, OAUTH), {"thread_id": "t1"})
    bodies = [m["body"] for m in result.vars["messages"]]
    assert bodies == ["Plain hello", "Only\xa0HTML\nline 2"] and result.vars["subject"] == "Hi"


def test_get_draft(http):
    http.on("GET", "/drafts/d1", {"id": "d1", "message": {"id": "m9", "payload": {"headers": [{"name": "To", "value": "x@y.z"}],
                                                                                  "mimeType": "text/plain", "body": {"data": b64("Draft text")}}}})
    result = run(make_tool(GmailGetDraftTool, OAUTH), {"draft_id": "d1"})
    assert result.vars["to"] == "x@y.z" and result.vars["body"] == "Draft text"


def test_ids_are_encoded(http):
    run(make_tool(GmailTrashMessageTool, OAUTH), {"message_id": "../labels/x"})
    assert http.calls[0].url == f"{API}/messages/..%2Flabels%2Fx/trash"


def test_original_tool_with_oauth_and_per_user(http):
    http.on("GET", "/messages", {"messages": []})
    result = run(make_tool(SearchMessagesTool, OAUTH), {"query": "from:bob"})
    assert http.calls[0].url.startswith(f"{API}/messages") and result.messages
    per_user = run(make_tool(SearchMessagesTool, PER_USER), {"query": "from:bob"})
    assert "/gmail/callback?start=" in per_user.texts[0]


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
def test_each_tool_yaml_points_to_one_tool_class(tool_file):
    spec = yaml.safe_load((ROOT / tool_file).read_text(encoding="utf-8"))
    assert (ROOT / spec["extra"]["python"]["source"]).exists()
    tool_class(spec)


@pytest.mark.parametrize("tool_file", [f for f in PROVIDER["tools"] if "/gmail_" in f])
def test_new_tools_emit_every_declared_output(tool_file, http):
    spec = yaml.safe_load((ROOT / tool_file).read_text(encoding="utf-8"))
    result = run(make_tool(tool_class(spec), {}))
    assert set(result.vars) == set(spec["output_schema"]["properties"]) and result.vars["success"] is False


def test_manifest_and_endpoint():
    manifest = yaml.safe_load((ROOT / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["version"] == "1.0.0" and manifest["plugins"]["endpoints"] == ["group/gmail_signin.yaml"]
    group = yaml.safe_load((ROOT / "group" / "gmail_signin.yaml").read_text(encoding="utf-8"))
    assert yaml.safe_load((ROOT / group["endpoints"][0]).read_text(encoding="utf-8"))["path"] == "/gmail/callback"


def load_provider():
    """provider/dify-gmail.py has a hyphen in its name, so it is loaded by path."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("dify_gmail_provider", ROOT / "provider" / "dify-gmail.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.DifyGmailProvider


def test_provider_validation(http):
    provider_class = load_provider()
    provider = provider_class.__new__(provider_class)
    provider._validate_credentials(PER_USER)
    assert http.calls == []
    with pytest.raises(ToolProviderCredentialValidationError, match="/gmail/callback"):
        provider._validate_credentials({**PER_USER, "redirect_uri": "https://dify.example.com/e/x/google_calendar/callback"})

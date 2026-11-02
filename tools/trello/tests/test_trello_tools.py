import importlib
import inspect
from pathlib import Path

import pytest
import requests
import yaml
from dify_plugin import Tool

from tests.fakes import API, PER_USER, TOKEN, FakeHttp, FakeResponse, make_tool, run
from tools import trello_http
from tools.fetch_all_boards import FetchAllBoardsTool
from tools.trello_add_attachment import TrelloAddAttachmentTool
from tools.trello_add_card_label import TrelloAddCardLabelTool
from tools.trello_add_comment import TrelloAddCommentTool
from tools.trello_create_checklist import TrelloCreateChecklistTool
from tools.trello_create_label import TrelloCreateLabelTool
from tools.trello_get_attachment import TrelloGetAttachmentTool
from tools.trello_get_card import TrelloGetCardTool
from tools.trello_invite_board_member import TrelloInviteBoardMemberTool
from tools.trello_list_checklists import TrelloListChecklistsTool
from tools.trello_list_comments import TrelloListCommentsTool
from tools.trello_search import TrelloSearchTool
from tools.trello_sign_out import SignOutTool
from tools.trello_update_checklist_item import TrelloUpdateChecklistItemTool
from tools.trello_update_list import TrelloUpdateListTool
from tools.update_card import UpdateCardByIdTool

ROOT = Path(__file__).resolve().parents[1]
PROVIDER = yaml.safe_load((ROOT / "provider" / "trello.yaml").read_text(encoding="utf-8"))
AUTH = 'OAuth oauth_consumer_key="app-key", oauth_token="shared-token"'
CARD = {"id": "c1", "name": "Fix login", "desc": "Steps", "idList": "l1", "idBoard": "b1", "due": "2030-01-01T00:00:00.000Z",
        "dueComplete": False, "labels": [{"name": "bug", "color": "red"}], "idMembers": ["m1"], "shortUrl": "https://trello.com/c/abc",
        "list": {"name": "Doing"}, "members": [{"id": "m1", "username": "alice", "fullName": "Alice"}],
        "checklists": [{"id": "k1", "name": "QA", "idCard": "c1", "checkItems": [
            {"id": "i2", "name": "two", "state": "incomplete", "pos": 2}, {"id": "i1", "name": "one", "state": "complete", "pos": 1}]}],
        "attachments": [{"id": "a1", "name": "log.txt", "bytes": 3, "mimeType": "text/plain", "isUpload": True,
                         "url": "https://trello.com/1/cards/c1/attachments/a1/download/log.txt"}]}


@pytest.fixture
def http(monkeypatch):
    return FakeHttp().install(monkeypatch)


def test_shim_moves_key_and_token_out_of_the_url(monkeypatch):
    sent = []
    monkeypatch.setattr(trello_http._requests, "request", lambda method, url, **kw: sent.append((method, url, kw)) or FakeResponse([]))
    trello_http.get(f"{API}/boards/b1?filter=open&key=K&token=T")
    trello_http.post(f"{API}/cards", params={"name": "x", "key": "K", "token": "T", "desc": None})
    (m1, url1, kw1), (m2, url2, kw2) = sent
    assert url1 == f"{API}/boards/b1?filter=open" and "token" not in url1
    assert kw1["headers"]["Authorization"] == 'OAuth oauth_consumer_key="K", oauth_token="T"'
    assert kw2["params"] == {"name": "x"} and kw2["headers"]["Authorization"].endswith('oauth_token="T"')


def test_original_tool_sends_no_token_in_url(monkeypatch):
    sent = []

    def send(session, request, **kwargs):
        sent.append(request)
        r = requests.Response()
        r.status_code = 200
        r._content = b'[{"name": "Roadmap", "id": "b1"}]'
        r.request = request
        return r

    monkeypatch.setattr(requests.Session, "send", send)
    result = run(make_tool(FetchAllBoardsTool, TOKEN), {"boards": "open"})
    assert result.texts == ["Boards: Roadmap (ID: b1)"]
    assert "token" not in sent[0].url and "key=" not in sent[0].url
    assert sent[0].headers["Authorization"] == AUTH


def test_original_tool_returns_the_sign_in_link_per_user(http):
    result = run(make_tool(FetchAllBoardsTool, PER_USER), {})
    assert "https://trello.com/1/authorize?" in result.texts[0] and http.calls == []


def test_update_card_accepts_more_fields(monkeypatch):
    sent = []
    monkeypatch.setattr(trello_http._requests, "request", lambda method, url, **kw: sent.append((method, url, kw)) or FakeResponse({}))
    run(make_tool(UpdateCardByIdTool, TOKEN), {"id": "c1", "dueComplete": True, "idLabels": "l1,l2", "pos": "top"})
    assert sent[0][2]["params"] == {"dueComplete": True, "idLabels": "l1,l2", "pos": "top"}


def test_get_card(http):
    http.on("GET", "/cards/c1", CARD)
    result = run(make_tool(TrelloGetCardTool, TOKEN), {"card_id": "c1"})
    card = result.vars["card"]
    assert card["list_name"] == "Doing" and card["labels"] == ["bug"] and card["members"][0]["username"] == "alice"
    assert [i["name"] for i in card["checklists"][0]["items"]] == ["one", "two"] and card["checklists"][0]["completed"] == 1
    assert "QA 1/2" in result.texts[-1]
    assert http.calls[0].headers["Authorization"] == AUTH and "token" not in http.calls[0].params


def test_search(http):
    http.on("GET", "/search", {"cards": [CARD], "boards": [{"id": "b1", "name": "Roadmap", "url": "u"}]})
    result = run(make_tool(TrelloSearchTool, TOKEN), {"query": "login", "board_id": "b1", "limit": 5})
    assert result.vars["count"] == 1 and result.vars["boards"][0]["name"] == "Roadmap"
    assert http.calls[0].params["idBoards"] == "b1" and http.calls[0].params["cards_limit"] == 5


def test_comments(http):
    http.on("POST", "/cards/c1/actions/comments", {"id": "x1", "data": {"text": "hi"}, "memberCreator": {"fullName": "Alice"}})
    http.on("GET", "/cards/c1/actions", [{"id": "x1", "data": {"text": "hi"}, "memberCreator": {"fullName": "Alice"}, "date": "d"}])
    assert run(make_tool(TrelloAddCommentTool, TOKEN), {"card_id": "c1", "text": "hi"}).vars["comment_id"] == "x1"
    assert http.calls[0].json == {"text": "hi"}
    listed = run(make_tool(TrelloListCommentsTool, TOKEN), {"card_id": "c1"})
    assert listed.vars["comments"] == [{"id": "x1", "text": "hi", "author": "Alice", "date": "d"}]
    assert http.calls[1].params["filter"] == "commentCard"


def test_checklists(http):
    http.on("POST", f"{API}/checklists", {"id": "k9", "name": "Launch", "idCard": "c1"})
    http.on("POST", "/checklists/k9/checkItems", {"id": "i9"})
    http.on("GET", "/cards/c1/checklists", CARD["checklists"])
    http.on("PUT", "/cards/c1/checkItem/i2", {"id": "i2", "name": "two", "state": "complete"})
    created = run(make_tool(TrelloCreateChecklistTool, TOKEN), {"card_id": "c1", "name": "Launch", "items": "a, b"})
    assert created.vars["checklist_id"] == "k9" and [c.json for c in http.calls[1:3]] == [{"name": "a"}, {"name": "b"}]
    listed = run(make_tool(TrelloListChecklistsTool, TOKEN), {"card_id": "c1"})
    assert "[x] one" in listed.texts[-1] and "[ ] two" in listed.texts[-1]
    done = run(make_tool(TrelloUpdateChecklistItemTool, TOKEN), {"card_id": "c1", "item_id": "i2", "complete": True})
    assert done.vars["state"] == "complete" and http.calls[-1].json == {"state": "complete"}
    nothing = run(make_tool(TrelloUpdateChecklistItemTool, TOKEN), {"card_id": "c1", "item_id": "i2"})
    assert "Nothing to update" in nothing.vars["error"]


def test_labels(http):
    http.on("POST", f"{API}/labels", {"id": "lb1", "name": "urgent", "color": "red"})
    http.on("POST", "/cards/c1/idLabels", ["lb1"])
    assert run(make_tool(TrelloCreateLabelTool, TOKEN), {"board_id": "b1", "name": "urgent", "color": "red"}).vars["label_id"] == "lb1"
    assert http.calls[0].json == {"idBoard": "b1", "name": "urgent", "color": "red"}
    bad = run(make_tool(TrelloCreateLabelTool, TOKEN), {"board_id": "b1", "name": "x", "color": "beige"})
    assert "Unknown label color" in bad.vars["error"]
    assert run(make_tool(TrelloAddCardLabelTool, TOKEN), {"card_id": "c1", "label_id": "lb1"}).vars["added"]
    assert http.calls[-1].json == {"value": "lb1"}


def test_update_list_archive(http):
    http.on("PUT", "/lists/l1", {"id": "l1", "name": "Done", "closed": True})
    result = run(make_tool(TrelloUpdateListTool, TOKEN), {"list_id": "l1", "archived": "true"})
    assert result.vars["archived"] is True and http.calls[0].json == {"closed": True}


def test_invite_member_validates_role(http):
    http.on("PUT", "/boards/b1/members", {})
    assert run(make_tool(TrelloInviteBoardMemberTool, TOKEN), {"board_id": "b1", "email": "a@b.c", "type": "admin"}).vars["invited"]
    assert http.calls[0].json == {"email": "a@b.c", "type": "admin"}
    assert "type must be" in run(make_tool(TrelloInviteBoardMemberTool, TOKEN), {"board_id": "b1", "email": "a@b.c", "type": "owner"}).vars["error"]


def test_attachments(http):
    http.on("POST", "/cards/c1/attachments", {"id": "a2", "name": "notes.txt", "bytes": 5, "isUpload": True})
    up = run(make_tool(TrelloAddAttachmentTool, TOKEN), {"card_id": "c1", "file_content": "hello", "name": "notes.txt"})
    assert up.vars["attachment_id"] == "a2" and http.calls[0].files["file"] == ("notes.txt", b"hello", "text/plain")
    link = run(make_tool(TrelloAddAttachmentTool, TOKEN), {"card_id": "c1", "url": "javascript:alert(1)"})
    assert "http(s) link" in link.vars["error"]

    http.on("GET", "/cards/c1/attachments/a1/download/log.txt", FakeResponse(None, 200, content=b"abc"))
    http.on("GET", "/cards/c1/attachments/a1", CARD["attachments"][0])
    got = run(make_tool(TrelloGetAttachmentTool, TOKEN), {"card_id": "c1", "attachment_id": "a1"})
    assert got.blobs[0][1] == b"abc" and got.blobs[0][2] == {"mime_type": "text/plain", "filename": "log.txt"}
    assert all(c.url.startswith(API + "/") for c in http.calls)


def test_ids_cannot_change_the_path(http):
    run(make_tool(TrelloGetCardTool, TOKEN), {"card_id": "../members/me"})
    assert http.calls[0].url == f"{API}/cards/..%2Fmembers%2Fme"


def test_errors_become_tool_errors(http):
    http.on("GET", "/cards/zz", FakeResponse(None, 400, content=b"invalid id"))
    result = run(make_tool(TrelloGetCardTool, TOKEN), {"card_id": "zz"})
    assert result.vars["error"].startswith("Trello API error 400: invalid id")


def test_sign_out_modes(http):
    assert "only applies" in run(make_tool(SignOutTool, TOKEN)).texts[0]
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


def test_new_tools_are_prefixed_and_unique():
    names = [yaml.safe_load((ROOT / f).read_text(encoding="utf-8"))["identity"]["name"] for f in PROVIDER["tools"]]
    assert len(names) == len(set(names)) == 43
    assert sum(n.startswith("trello_") for n in names) == 30


@pytest.mark.parametrize("tool_file", [f for f in PROVIDER["tools"] if "/trello_" in f])
def test_new_tools_emit_every_declared_output(tool_file, http):
    spec = yaml.safe_load((ROOT / tool_file).read_text(encoding="utf-8"))
    result = run(make_tool(tool_class(spec), {"trello_api_key": ""}))
    assert set(result.vars) == set(spec["output_schema"]["properties"])
    assert result.vars["success"] is False and result.vars["error"]


def test_manifest_and_endpoints():
    manifest = yaml.safe_load((ROOT / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["version"] == "1.0.0" and manifest["plugins"]["endpoints"] == ["group/trello_signin.yaml"]
    group = yaml.safe_load((ROOT / "group" / "trello_signin.yaml").read_text(encoding="utf-8"))
    routes = {(e["method"], e["path"]) for e in (yaml.safe_load((ROOT / f).read_text(encoding="utf-8")) for f in group["endpoints"])}
    assert routes == {("GET", "/trello/callback"), ("POST", "/trello/callback")}


def test_provider_validation(http):
    from dify_plugin.errors.tool import ToolProviderCredentialValidationError

    from provider.trello import TrelloProvider

    provider = TrelloProvider.__new__(TrelloProvider)
    http.on("GET", "/members/me", {"username": "a"})
    provider._validate_credentials(TOKEN)
    assert http.calls[0].headers["Authorization"] == AUTH
    http.routes.clear()
    http.on("GET", "/members/me", FakeResponse({}, 401))
    with pytest.raises(ToolProviderCredentialValidationError, match="Unauthorized"):
        provider._validate_credentials(TOKEN)
    provider._validate_credentials(PER_USER)
    for change, message in [({"trello_api_secret": ""}, "API secret"), ({"redirect_uri": "http://localhost/e/x/trello/callback"}, "localhost"),
                            ({"redirect_uri": "https://d/e/x/jira/callback"}, "/trello/callback")]:
        with pytest.raises(ToolProviderCredentialValidationError, match=message):
            provider._validate_credentials({**PER_USER, **change})




def test_create_board_uses_the_first_workspace(monkeypatch):
    from tools import create_board

    sent = []

    def fake(method, url, **kw):
        sent.append((method, url, kw))
        return FakeResponse([{"id": "org1", "displayName": "Team"}] if method == "GET" else {"name": "B", "id": "b9"})

    monkeypatch.setattr(trello_http._requests, "request", fake)
    result = run(make_tool(create_board.CreateBoardTool, TOKEN), {"name": "B"})
    assert sent[0][1] == f"{API}/members/me/organizations"
    assert sent[1][2]["params"] == {"name": "B", "idOrganization": "org1"}
    assert "ID: b9" in result.texts[-1]

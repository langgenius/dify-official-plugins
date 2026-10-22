import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from tools import graph_client
from tools.graph_client import GraphError, check_next_link, resolve_graph_context
from tools.list_chat_messages import ListChatMessagesTool
from tools.list_chats import ListChatsTool

OAUTH = {"access_token": "user-token", "refresh_token": "r"}
G = "https://graph.microsoft.com/v1.0"
CHAT_ID = "19:abc@thread.v2"


class FakeResponse:
    def __init__(self, payload=None, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.content = b"" if payload is None else json.dumps(payload).encode()
        self.text = self.content.decode()

    def json(self):
        return self._payload


class Graph:
    """Fake requests.request: answers /me, and serves queued pages for everything else."""

    def __init__(self, pages, me="me-id"):
        self.pages, self.me, self.calls = list(pages), me, []

    def __call__(self, method, url, headers=None, params=None, json=None, timeout=None):
        self.calls.append(SimpleNamespace(method=method, url=url, params=params))
        if url == f"{G}/me":
            return FakeResponse({"id": self.me})
        page = self.pages.pop(0)
        return page if isinstance(page, FakeResponse) else FakeResponse(page)


@pytest.fixture
def graph(monkeypatch):
    def install(pages, **kw):
        fake = Graph(pages, **kw)
        monkeypatch.setattr(graph_client.requests, "request", fake)
        return fake

    return install


def run(cls, params):
    tool = cls.__new__(cls)
    tool.runtime = SimpleNamespace(credentials=OAUTH)
    tool.create_text_message = lambda text: ("text", text)
    tool.create_json_message = lambda data: ("json", data)
    return list(tool._invoke(params))


def member(name, uid, email):
    return {"displayName": name, "userId": uid, "email": email, "tenantId": "t1"}


# ── list_chats ────────────────────────────────────────────────────────


def test_list_chats_builds_the_filter_for_name_email_and_type(graph):
    fake = graph([{"value": []}])
    run(ListChatsTool, {"participant_name": "O'Brien", "participant_email": "ob@contoso.com", "chat_type": "oneOnOne", "top": 10})
    params = fake.calls[0].params
    assert params["$expand"] == "members" and params["$top"] == 10
    assert params["$filter"] == (
        "members/any(o: o/displayName eq 'O''Brien' and o/microsoft.graph.aadUserConversationMember/email eq 'ob@contoso.com')"
        " and chatType eq 'oneOnOne'"
    )


def test_list_chats_without_filters_sends_no_filter(graph):
    fake = graph([{"value": []}])
    run(ListChatsTool, {})
    assert "$filter" not in fake.calls[0].params


def test_list_chats_returns_members_display_name_and_marks_me(graph):
    graph([{"value": [
        {"id": "c1", "topic": None, "chatType": "oneOnOne", "webUrl": "https://teams/c1",
         "members": [member("Me", "me-id", "me@contoso.com"), member("Kim", "u2", "kim@contoso.com")]},
        {"id": "c2", "topic": "Launch", "chatType": "group", "members": [member("Me", "me-id", "me@contoso.com")]},
        {"id": "c3", "topic": None, "chatType": "oneOnOne", "members": [member("Me", "me-id", "me@contoso.com")]},
    ]}])
    out = run(ListChatsTool, {})
    chats = out[1][1]["chats"]
    assert chats[0]["display_name"] == "Kim"
    assert [m["is_me"] for m in chats[0]["members"]] == [True, False]
    assert chats[0]["members"][1] == {"name": "Kim", "user_id": "u2", "email": "kim@contoso.com", "tenant_id": "t1", "is_me": False}
    assert chats[1]["display_name"] == "Launch"
    # Only the signed-in user came back: the other party is not guessed.
    assert chats[2]["display_name"] is None
    assert out[1][1]["pagination"] == {"complete": True, "has_more": False, "next_link": None, "pages_read": 1}


def test_list_chats_follows_empty_pages_until_the_link_ends(graph):
    fake = graph([
        {"value": [], "@odata.nextLink": f"{G}/me/chats?$skiptoken=1"},
        {"value": [], "@odata.nextLink": f"{G}/me/chats?$skiptoken=2"},
        {"value": [{"id": "c9", "chatType": "group", "members": []}]},
    ])
    out = run(ListChatsTool, {"participant_name": "Kim"})
    assert [c["id"] for c in out[1][1]["chats"]] == ["c9"]
    assert out[1][1]["pagination"]["pages_read"] == 3
    assert fake.calls[1].params is None  # the next link carries the query


def test_list_chats_stops_at_max_pages_and_returns_the_resume_link(graph):
    graph([{"value": [{"id": "c1", "members": []}], "@odata.nextLink": f"{G}/me/chats?$skiptoken=2"}])
    out = run(ListChatsTool, {"max_pages": 1})
    assert out[1][1]["pagination"] == {"complete": False, "has_more": True, "next_link": f"{G}/me/chats?$skiptoken=2", "pages_read": 1}
    assert "pass next_link" in out[0][1]


def test_list_chats_error_midway_keeps_what_was_read(graph):
    graph([
        {"value": [{"id": "c1", "members": []}], "@odata.nextLink": f"{G}/me/chats?$skiptoken=2"},
        FakeResponse({"error": {"code": "TooManyRequests", "message": "slow down"}}, 429),
    ])
    out = run(ListChatsTool, {})
    data = out[1][1]
    assert [c["id"] for c in data["chats"]] == ["c1"]
    assert data["pagination"]["next_link"] == f"{G}/me/chats?$skiptoken=2"
    assert "429" in data["warning"]


def test_list_chats_error_on_the_first_page_is_an_error(graph):
    graph([FakeResponse({"error": {"code": "Forbidden", "message": "no"}}, 403)])
    out = run(ListChatsTool, {})
    assert out[1][1]["error"].startswith("API error 403")


def test_list_chats_resumes_from_next_link_without_new_filters(graph):
    fake = graph([{"value": []}])
    run(ListChatsTool, {"next_link": f"{G}/me/chats?$skiptoken=abc", "participant_name": "ignored"})
    assert fake.calls[0].url == f"{G}/me/chats?$skiptoken=abc" and fake.calls[0].params is None


@pytest.mark.parametrize("value", ["all", "", None])
def test_list_chats_chat_type_all(graph, value):
    fake = graph([{"value": []}])
    run(ListChatsTool, {"chat_type": value})
    assert "$filter" not in fake.calls[0].params


@pytest.mark.parametrize("params, message", [({"chat_type": "channel"}, "chat_type"), ({"top": 51}, "top"), ({"max_pages": 0}, "max_pages")])
def test_list_chats_validates_input(graph, params, message):
    graph([])
    assert message in run(ListChatsTool, params)[0][1]


# ── next_link checks ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "link",
    [
        "https://evil.example/v1.0/me/chats?$skiptoken=1",
        f"{G}/me/chats/other?$skiptoken=1",
        "https://graph.microsoft.com/beta/me/chats?$skiptoken=1",
        f"{G}/chats/19:other@thread.v2/messages?$skiptoken=1",
    ],
)
def test_foreign_next_links_are_refused(link):
    ctx = resolve_graph_context(OAUTH)
    with pytest.raises(GraphError, match="next_link"):
        check_next_link(ctx, link, "/me/chats" if "/me/" in link or "evil" in link or "beta" in link else f"/chats/{graph_client.segment(CHAT_ID)}/messages")


def test_users_form_of_me_chats_is_accepted():
    ctx = resolve_graph_context(OAUTH)
    assert check_next_link(ctx, f"{G}/users/me-id/chats?$skiptoken=1", "/me/chats")


def test_next_link_follows_the_credential_cloud():
    ctx = resolve_graph_context({"access_token": "t", "graph_base_url": "https://microsoftgraph.chinacloudapi.cn"})
    assert check_next_link(ctx, "https://microsoftgraph.chinacloudapi.cn/v1.0/me/chats?$skiptoken=1", "/me/chats")
    with pytest.raises(GraphError):
        check_next_link(ctx, f"{G}/me/chats?$skiptoken=1", "/me/chats")


# ── list_chat_messages ────────────────────────────────────────────────


MESSAGES = {"value": [
    {"id": "m2", "messageType": "message", "chatId": CHAT_ID, "createdDateTime": "2026-10-14T03:00:00Z",
     "from": {"user": {"id": "u2", "displayName": "Kim"}}, "body": {"contentType": "html", "content": "<p>hi</p>"},
     "attachments": [{"id": "a1", "name": "f.pdf", "contentType": "reference", "contentUrl": "https://x/f.pdf"}]},
    {"id": "m1", "messageType": "systemEventMessage", "eventDetail": {"@odata.type": "#microsoft.graph.membersAddedEventMessageDetail"}},
]}


def test_messages_default_newest_first_by_created_time_without_system_events(graph):
    fake = graph([MESSAGES])
    out = run(ListChatMessagesTool, {"chat_id": CHAT_ID, "top": 5})
    call = fake.calls[0]
    assert call.url == f"{G}/chats/19%3Aabc%40thread.v2/messages"
    assert call.params == {"$top": 5, "$orderby": "createdDateTime desc"}
    msgs = out[1][1]["messages"]
    assert [m["id"] for m in msgs] == ["m2"]
    assert msgs[0]["from"] == {"id": "u2", "name": "Kim", "kind": "user"}
    assert msgs[0]["body"] == "<p>hi</p>" and msgs[0]["content_type"] == "html"
    assert msgs[0]["attachments"][0]["name"] == "f.pdf"


def test_messages_can_include_system_events(graph):
    graph([MESSAGES])
    out = run(ListChatMessagesTool, {"chat_id": CHAT_ID, "include_system_events": True})
    assert [m["id"] for m in out[1][1]["messages"]] == ["m2", "m1"]
    assert out[1][1]["messages"][1]["from"] is None


def test_messages_end_filter_on_created_time_is_converted_to_utc(graph):
    fake = graph([{"value": []}])
    run(ListChatMessagesTool, {"chat_id": CHAT_ID, "end_datetime": "2026-10-01T09:00:00+09:00"})
    assert fake.calls[0].params["$filter"] == "createdDateTime lt 2026-10-01T00:00:00Z"


def test_messages_modified_time_range(graph):
    fake = graph([{"value": []}])
    run(ListChatMessagesTool, {"chat_id": CHAT_ID, "time_field": "lastModifiedDateTime",
                               "start_datetime": "2026-10-14T00:00:00+09:00", "end_datetime": "2026-10-15T00:00:00+09:00"})
    params = fake.calls[0].params
    assert params["$orderby"] == "lastModifiedDateTime desc"
    assert params["$filter"] == "lastModifiedDateTime gt 2026-10-13T15:00:00Z and lastModifiedDateTime lt 2026-10-14T15:00:00Z"


@pytest.mark.parametrize(
    "params, message",
    [
        ({}, "chat_id is required"),
        ({"chat_id": CHAT_ID, "start_datetime": "2026-10-14T00:00:00+09:00"}, "lastModifiedDateTime"),
        ({"chat_id": CHAT_ID, "end_datetime": "2026-10-14T00:00:00"}, "time zone"),
        ({"chat_id": CHAT_ID, "time_field": "sentDateTime"}, "time_field"),
    ],
)
def test_messages_validate_input(graph, params, message):
    graph([])
    assert message in run(ListChatMessagesTool, params)[0][1]


def test_messages_resume_only_for_the_same_chat(graph):
    fake = graph([{"value": []}])
    link = f"{G}/chats/{CHAT_ID}/messages?$skiptoken=x"
    run(ListChatMessagesTool, {"chat_id": CHAT_ID, "next_link": link})
    assert fake.calls[0].url == link
    out = run(ListChatMessagesTool, {"chat_id": "19:other@thread.v2", "next_link": link})
    assert "next_link must be" in out[0][1]


def test_pagination_stops_on_the_time_budget(graph, monkeypatch):
    clock = iter([0, 100, 200, 300])
    monkeypatch.setattr(graph_client.time, "monotonic", lambda: next(clock))
    graph([
        {"value": [{"id": "c1", "members": []}], "@odata.nextLink": f"{G}/me/chats?$skiptoken=2"},
        {"value": [{"id": "c2", "members": []}]},
    ])
    out = run(ListChatsTool, {})
    assert [c["id"] for c in out[1][1]["chats"]] == ["c1"]
    assert out[1][1]["pagination"]["has_more"] is True


def test_query_is_not_double_encoded(graph):
    fake = graph([{"value": []}])
    run(ListChatsTool, {"participant_name": "김 철수"})
    # requests encodes params itself; the plugin passes the raw OData expression.
    assert "김 철수" in fake.calls[0].params["$filter"]
    assert parse_qs(urlparse(fake.calls[0].url).query) == {}

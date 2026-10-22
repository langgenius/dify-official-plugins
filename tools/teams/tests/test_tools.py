import json
from types import SimpleNamespace

import pytest

from tools import graph_client
from tools.create_chat import CreateChatTool
from tools.create_online_meeting import CreateOnlineMeetingTool
from tools.create_planner_task import CreatePlannerTaskTool
from tools.delete_planner_task import DeletePlannerTaskTool
from tools.list_planner_tasks import ListPlannerTasksTool
from tools.list_teams import ListTeamsTool
from tools.reply_channel_message import ReplyChannelMessageTool
from tools.update_planner_task import UpdatePlannerTaskTool

OAUTH = {"access_token": "user-token", "refresh_token": "r"}


class FakeResponse:
    def __init__(self, payload=None, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.content = b"" if payload is None else json.dumps(payload).encode()
        self.text = self.content.decode()

    def json(self):
        return self._payload


class FakeGraph:
    """Records every call to requests.request and answers from a route table."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, method, url, headers=None, params=None, json=None, timeout=None):
        self.calls.append(SimpleNamespace(method=method, url=url, headers=headers or {}, params=params, json=json))
        for (m, suffix), response in self.routes.items():
            if m == method and url.endswith(suffix):
                return response() if callable(response) else response
        raise AssertionError(f"unexpected {method} {url}")


@pytest.fixture
def graph(monkeypatch):
    def install(routes):
        fake = FakeGraph(routes)
        monkeypatch.setattr(graph_client.requests, "request", fake)
        return fake

    return install


def run(cls, params, credentials=OAUTH):
    tool = cls.__new__(cls)
    tool.runtime = SimpleNamespace(credentials=credentials)
    tool.create_text_message = lambda text: ("text", text)
    tool.create_json_message = lambda data: ("json", data)
    return list(tool._invoke(params))


def test_reply_posts_to_the_thread_with_quoted_ids(graph):
    fake = graph({("POST", "/replies"): FakeResponse({"id": "r1"}, 201)})
    out = run(ReplyChannelMessageTool, {"team_id": "t1", "channel_id": "19:c@thread.tacv2", "message_id": "m1", "message": "hi"})
    call = fake.calls[0]
    assert call.url == "https://graph.microsoft.com/v1.0/teams/t1/channels/19%3Ac%40thread.tacv2/messages/m1/replies"
    assert call.json == {"body": {"contentType": "html", "content": "hi"}}
    assert out[0] == ("text", "Reply posted. Reply ID: r1")


def test_reply_requires_message_id(graph):
    graph({})
    out = run(ReplyChannelMessageTool, {"team_id": "t1", "channel_id": "c", "message": "hi"})
    assert out == [("text", "message_id is required.")]


def test_create_chat_one_on_one_includes_the_signed_in_user(graph):
    fake = graph({("GET", "/me"): FakeResponse({"id": "me-id"}), ("POST", "/chats"): FakeResponse({"id": "c1", "chatType": "oneOnOne"}, 201)})
    run(CreateChatTool, {"members": "a@contoso.com"})
    body = fake.calls[1].json
    assert body["chatType"] == "oneOnOne"
    binds = [m["user@odata.bind"] for m in body["members"]]
    assert binds == ["https://graph.microsoft.com/v1.0/users('me-id')", "https://graph.microsoft.com/v1.0/users('a@contoso.com')"]
    assert "topic" not in body


def test_create_chat_with_topic_is_a_group_chat(graph):
    fake = graph({("GET", "/me"): FakeResponse({"id": "me-id"}), ("POST", "/chats"): FakeResponse({"id": "c1", "chatType": "group"}, 201)})
    run(CreateChatTool, {"members": "a@contoso.com", "topic": "Launch"})
    assert fake.calls[1].json["chatType"] == "group"
    assert fake.calls[1].json["topic"] == "Launch"


def test_online_meeting_times_are_sent_in_utc(graph):
    fake = graph({("POST", "/me/onlineMeetings"): FakeResponse({"id": "om1", "joinWebUrl": "https://teams/join"}, 201)})
    out = run(CreateOnlineMeetingTool, {"subject": "s", "start_datetime": "2026-12-01T10:00:00+09:00", "end_datetime": "2026-12-01T10:30:00+09:00"})
    assert fake.calls[0].json == {"subject": "s", "startDateTime": "2026-12-01T01:00:00Z", "endDateTime": "2026-12-01T01:30:00Z"}
    assert "taken as UTC" not in out[0][1]


def test_online_meeting_rejects_end_before_start(graph):
    graph({})
    out = run(CreateOnlineMeetingTool, {"subject": "s", "start_datetime": "2026-12-01T10:00:00Z", "end_datetime": "2026-12-01T09:00:00Z"})
    assert out == [("text", "end_datetime must be after start_datetime.")]


def test_create_task_resolves_me_and_builds_assignments(graph):
    fake = graph({("GET", "/me"): FakeResponse({"id": "me-id"}), ("POST", "/planner/tasks"): FakeResponse({"id": "task1"}, 201)})
    out = run(CreatePlannerTaskTool, {"plan_id": "p1", "title": "Do it", "assignee_ids": "me, u2", "due_datetime": "2026-12-01"})
    body = fake.calls[-1].json
    assert body["planId"] == "p1" and body["title"] == "Do it"
    assert set(body["assignments"]) == {"me-id", "u2"}
    assert body["dueDateTime"] == "2026-12-01T00:00:00Z"
    assert "taken as UTC" in out[0][1]


def test_update_task_sends_the_etag(graph):
    fake = graph({
        ("GET", "/planner/tasks/task1"): FakeResponse({"id": "task1", "@odata.etag": 'W/"abc"'}),
        ("PATCH", "/planner/tasks/task1"): FakeResponse({"id": "task1", "percentComplete": 100}),
    })
    out = run(UpdatePlannerTaskTool, {"task_id": "task1", "percent_complete": 100})
    patch = fake.calls[1]
    assert patch.headers["If-Match"] == 'W/"abc"'
    assert patch.json == {"percentComplete": 100}
    assert out[0] == ("text", "Task updated: percentComplete.")


def test_update_task_needs_a_change(graph):
    graph({})
    out = run(UpdatePlannerTaskTool, {"task_id": "task1"})
    assert out[0][1].startswith("Nothing to update")


def test_update_task_rejects_out_of_range_percent(graph):
    graph({})
    out = run(UpdatePlannerTaskTool, {"task_id": "task1", "percent_complete": 150})
    assert "0 to 100" in out[0][1]


def test_delete_task_sends_the_etag(graph):
    fake = graph({
        ("GET", "/planner/tasks/task1"): FakeResponse({"@odata.etag": 'W/"e"'}),
        ("DELETE", "/planner/tasks/task1"): FakeResponse(None, 204),
    })
    out = run(DeletePlannerTaskTool, {"task_id": "task1"})
    assert fake.calls[1].headers["If-Match"] == 'W/"e"'
    assert out[0] == ("text", "Task deleted.")


def test_list_tasks_follows_next_link_only_on_the_same_host(graph):
    page1 = FakeResponse({"value": [{"id": "1", "percentComplete": 0}], "@odata.nextLink": "https://graph.microsoft.com/v1.0/planner/plans/p1/tasks?$skiptoken=x"})
    page2 = FakeResponse({"value": [{"id": "2", "percentComplete": 100}], "@odata.nextLink": "https://evil.example/next"})
    pages = iter([page1, page2])
    fake = graph({("GET", "/tasks"): lambda: next(pages), ("GET", "skiptoken=x"): lambda: next(pages)})
    out = run(ListPlannerTasksTool, {"plan_id": "p1", "include_completed": False})
    assert len(fake.calls) == 2
    assert [t["id"] for t in out[1][1]["tasks"]] == ["1"]


def test_graph_errors_are_explained(graph):
    graph({("POST", "/replies"): FakeResponse({"error": {"code": "Forbidden", "message": "Missing scope"}}, 403)})
    out = run(ReplyChannelMessageTool, {"team_id": "t", "channel_id": "c", "message_id": "m", "message": "x"})
    assert out[0][1].startswith("API error 403: Forbidden: Missing scope")
    assert "delegated permission" in out[0][1]


def test_existing_tool_uses_the_credential_cloud(monkeypatch):
    seen = {}

    def fake_get(url, headers=None, timeout=None, **kwargs):
        seen["url"] = url
        return FakeResponse({"value": []})

    import tools.list_teams as list_teams_module

    monkeypatch.setattr(list_teams_module.requests, "get", fake_get)
    run(ListTeamsTool, {}, {"access_token": "t", "graph_base_url": "https://microsoftgraph.chinacloudapi.cn"})
    assert seen["url"] == "https://microsoftgraph.chinacloudapi.cn/v1.0/me/joinedTeams"

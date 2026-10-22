from types import SimpleNamespace

import pytest

import tools.send_message as send_module
import tools.list_messages as list_module
from tools import graph_client
from tools.list_messages import ListEmailsTool
from tools.send_message import SendMessageTool

SP = {
    "tenant_id": "contoso.onmicrosoft.com",
    "client_id": "app-id",
    "client_secret": "s3cret",
    "mailbox": "support@contoso.com",
}


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


def make_tool(cls, credentials):
    tool = cls.__new__(cls)
    tool.runtime = SimpleNamespace(credentials=credentials)
    tool.create_text_message = lambda text: ("text", text)
    tool.create_json_message = lambda data: ("json", data)
    return tool


@pytest.fixture
def app_token(monkeypatch):
    monkeypatch.setattr(
        graph_client.requests, "post", lambda *a, **k: FakeResponse({"access_token": "app", "expires_in": 3599})
    )


def test_send_message_with_service_principal_posts_to_the_mailbox(monkeypatch):
    sent = {}

    # graph_client and send_message share the same `requests` module, so one fake serves both
    def fake_post(url, data=None, headers=None, json=None, timeout=None):
        if "/oauth2/v2.0/token" in url:
            return FakeResponse({"access_token": "app", "expires_in": 3599})
        sent["url"] = url
        sent["auth"] = headers["Authorization"]
        return FakeResponse({}, 202)

    monkeypatch.setattr(send_module.requests, "post", fake_post)
    tool = make_tool(SendMessageTool, dict(SP))
    out = list(tool._invoke({"to": "a@b.com", "subject": "hi", "message": "body", "mailbox": "sales@contoso.com"}))

    assert sent["url"] == "https://graph.microsoft.com/v1.0/users/sales@contoso.com/sendMail"
    assert sent["auth"] == "Bearer app"
    assert out[0][0] == "text" and "sent successfully" in out[0][1]


def test_list_messages_with_oauth_still_uses_me(monkeypatch):
    seen = {}

    def fake_get(url, headers=None, params=None, timeout=None):
        seen["url"] = url
        return FakeResponse({"value": []})

    monkeypatch.setattr(list_module.requests, "get", fake_get)
    tool = make_tool(ListEmailsTool, {"access_token": "user", "refresh_token": "r"})
    list(tool._invoke({"limit": 5, "folder": "inbox"}))

    assert seen["url"] == "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages"


def test_tool_reports_missing_mailbox_instead_of_calling_graph(monkeypatch, app_token):
    monkeypatch.setattr(list_module.requests, "get", lambda *a, **k: pytest.fail("Graph must not be called"))
    tool = make_tool(ListEmailsTool, dict(SP, mailbox=""))
    out = list(tool._invoke({"limit": 5, "folder": "inbox"}))
    assert len(out) == 1 and out[0][0] == "text"
    assert "no signed-in user" in out[0][1]

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.get_channel_messages import GetChannelMessagesTool


class _Response:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = [] if body is None else body
        self.text = json.dumps(self._body)

    @property
    def is_success(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._body


def _tool(token="secret"):
    tool = object.__new__(GetChannelMessagesTool)
    tool.runtime = SimpleNamespace(credentials={"bot_token": token})
    tool.create_json_message = lambda value: {"type": "json", "value": value}
    tool.create_text_message = lambda value: {"type": "text", "value": value}
    return tool


def test_success_normalizes_messages_and_pagination(monkeypatch):
    from tools import get_channel_messages

    captured = {}
    body = [
        {
            "id": "2",
            "channel_id": "123",
            "author": {
                "id": "7",
                "username": "alice",
                "global_name": "Alice",
                "bot": False,
            },
            "content": "",
            "timestamp": "2026-01-02T00:00:00Z",
            "edited_timestamp": None,
            "attachments": [{"id": "a", "filename": "photo.png"}],
        },
        {"id": "1", "channel_id": "123", "author": {"id": "8", "username": "bot"}},
    ]

    def fake_get(url, headers=None, params=None, timeout=None):
        captured.update(
            {"url": url, "headers": headers, "params": params, "timeout": timeout}
        )
        return _Response(body=body)

    monkeypatch.setattr(get_channel_messages.httpx, "get", fake_get)
    messages = list(_tool()._invoke({"channel_id": "123", "limit": "20"}))

    assert captured["params"] == {"limit": 20}
    assert captured["headers"] == {"Authorization": "Bot secret"}
    assert messages[0]["value"]["count"] == 2
    assert messages[0]["value"]["order"] == "newest_to_oldest"
    assert messages[0]["value"]["next_before"] == "1"
    assert messages[0]["value"]["messages"][0]["attachments"] == body[0]["attachments"]
    assert messages[0]["value"]["messages"][1]["author_bot"] is False


@pytest.mark.parametrize(
    ("tool", "params", "error"),
    [
        (_tool(""), {"channel_id": "123"}, "Missing bot_token credential"),
        (_tool(), {}, "Missing required parameter: channel_id"),
        (
            _tool(),
            {"channel_id": "123", "limit": 101},
            "Invalid parameter: limit must be between 1 and 100",
        ),
        (
            _tool(),
            {"channel_id": "123", "limit": "20.5"},
            "Invalid parameter: limit must be an integer between 1 and 100",
        ),
        (
            _tool(),
            {"channel_id": "123", "before": "2", "after": "1"},
            "Invalid parameters: before and after cannot be used together",
        ),
    ],
)
def test_validation_errors_do_not_call_discord(monkeypatch, tool, params, error):
    from tools import get_channel_messages

    monkeypatch.setattr(
        get_channel_messages.httpx,
        "get",
        lambda *args, **kwargs: pytest.fail("Discord should not be called"),
    )
    assert list(tool._invoke(params)) == [{"type": "text", "value": error}]


@pytest.mark.parametrize("status_code", [401, 403, 429])
def test_discord_api_errors(monkeypatch, status_code):
    from tools import get_channel_messages

    monkeypatch.setattr(
        get_channel_messages.httpx,
        "get",
        lambda *args, **kwargs: _Response(status_code, {"message": "error"}),
    )
    result = list(_tool()._invoke({"channel_id": "123"}))
    assert result[0]["value"].startswith(f"Discord API error: status {status_code}")


def test_request_error(monkeypatch):
    from tools import get_channel_messages

    def fail(*args, **kwargs):
        raise httpx.RequestError("offline")

    monkeypatch.setattr(get_channel_messages.httpx, "get", fail)
    assert list(_tool()._invoke({"channel_id": "123"})) == [
        {"type": "text", "value": "Unable to fetch messages from Discord"}
    ]


def test_empty_message_list(monkeypatch):
    from tools import get_channel_messages

    monkeypatch.setattr(
        get_channel_messages.httpx, "get", lambda *args, **kwargs: _Response()
    )
    assert list(_tool()._invoke({"channel_id": "123"}))[0]["value"] == {
        "channel_id": "123",
        "count": 0,
        "order": "newest_to_oldest",
        "next_before": None,
        "messages": [],
    }

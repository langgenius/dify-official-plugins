import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.discord_webhook import DiscordWebhookTool


class _Response:
    def __init__(self, status_code=204, body=None):
        self.status_code = status_code
        self._body = body
        self.text = "" if body is None else json.dumps(body)
        self.content = b"" if body is None else self.text.encode()

    @property
    def is_success(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._body


def _tool():
    tool = object.__new__(DiscordWebhookTool)
    tool.runtime = SimpleNamespace(user_id="dify-user")
    tool.create_json_message = lambda value: {"type": "json", "value": value}
    tool.create_text_message = lambda value: {"type": "text", "value": value}
    return tool


def test_plain_text_payload_is_backward_compatible(monkeypatch):
    from tools import discord_webhook

    captured = {}

    def fake_post(url, headers=None, params=None, json=None, timeout=None):
        captured.update(
            {"url": url, "headers": headers, "params": params, "json": json, "timeout": timeout}
        )
        return _Response()

    monkeypatch.setattr(discord_webhook.httpx, "post", fake_post)
    result = list(
        _tool()._invoke(
            {
                "webhook_url": "https://discord.com/api/webhooks/123/token",
                "content": "Hello from Dify",
            }
        )
    )
    assert captured["params"] == {}
    assert captured["json"]["content"] == "Hello from Dify"
    assert result == [
        {"type": "text", "value": "Discord webhook message sent successfully"}
    ]


def test_rich_payload_and_wait_response(monkeypatch):
    from tools import discord_webhook

    captured = {}
    response_body = {"id": "42", "content": "Hello"}

    def fake_post(url, headers=None, params=None, json=None, timeout=None):
        captured.update({"params": params, "json": json})
        return _Response(200, response_body)

    monkeypatch.setattr(discord_webhook.httpx, "post", fake_post)
    result = list(
        _tool()._invoke(
            {
                "webhook_url": "https://discord.com/api/webhooks/123/token",
                "embeds_json": '[{"title": "Build finished"}]',
                "allowed_mentions_json": '{"parse": []}',
                "wait": True,
                "thread_id": "987",
            }
        )
    )
    assert captured["params"] == {"wait": "true", "thread_id": "987"}
    assert captured["json"]["embeds"] == [{"title": "Build finished"}]
    assert result[-1] == {"type": "json", "value": response_body}


def test_empty_message_is_rejected(monkeypatch):
    from tools import discord_webhook

    monkeypatch.setattr(
        discord_webhook.httpx,
        "post",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("Discord should not be called")
        ),
    )
    result = list(
        _tool()._invoke({"webhook_url": "https://discord.com/api/webhooks/123/token"})
    )
    assert result[0]["value"].startswith("Invalid message:")

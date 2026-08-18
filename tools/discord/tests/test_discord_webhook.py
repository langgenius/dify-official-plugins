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


class _MessageToolMixin:
    def create_json_message(self, value):
        return {"type": "json", "value": value}

    def create_text_message(self, value):
        return {"type": "text", "value": value}


def _tool():
    tool = object.__new__(DiscordWebhookTool)
    tool.runtime = SimpleNamespace(user_id="dify-user")
    tool.create_json_message = _MessageToolMixin.create_json_message.__get__(tool, DiscordWebhookTool)
    tool.create_text_message = _MessageToolMixin.create_text_message.__get__(tool, DiscordWebhookTool)
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

    messages = list(
        _tool()._invoke(
            {
                "webhook_url": "https://discord.com/api/webhooks/123/token",
                "content": "Hello from Dify",
            }
        )
    )

    assert captured == {
        "url": "https://discord.com/api/webhooks/123/token",
        "headers": {"Content-Type": "application/json"},
        "params": {},
        "json": {
            "username": "dify-user",
            "content": "Hello from Dify",
            "avatar_url": None,
        },
        "timeout": 20,
    }
    assert messages == [{"type": "text", "value": "Discord webhook message sent successfully"}]


def test_empty_message_returns_validation_error_without_calling_discord(monkeypatch):
    from tools import discord_webhook

    def fake_post(*args, **kwargs):
        raise AssertionError("Discord should not be called")

    monkeypatch.setattr(discord_webhook.httpx, "post", fake_post)

    messages = list(_tool()._invoke({"webhook_url": "https://discord.com/api/webhooks/123/token"}))

    assert messages == [
        {
            "type": "text",
            "value": "Invalid message: provide at least one of content, embeds_json, components_json, or poll_json",
        }
    ]


def test_invalid_json_returns_readable_error(monkeypatch):
    from tools import discord_webhook

    def fake_post(*args, **kwargs):
        raise AssertionError("Discord should not be called")

    monkeypatch.setattr(discord_webhook.httpx, "post", fake_post)

    messages = list(
        _tool()._invoke(
            {
                "webhook_url": "https://discord.com/api/webhooks/123/token",
                "embeds_json": "{not-json",
            }
        )
    )

    assert messages[0]["type"] == "text"
    assert messages[0]["value"].startswith("Invalid parameter embeds_json: malformed JSON")


def test_embeds_over_discord_limit_are_rejected(monkeypatch):
    from tools import discord_webhook

    def fake_post(*args, **kwargs):
        raise AssertionError("Discord should not be called")

    monkeypatch.setattr(discord_webhook.httpx, "post", fake_post)

    messages = list(
        _tool()._invoke(
            {
                "webhook_url": "https://discord.com/api/webhooks/123/token",
                "embeds_json": json.dumps([{"title": str(i)} for i in range(11)]),
            }
        )
    )

    assert messages == [{"type": "text", "value": "Invalid parameter embeds_json: Discord supports at most 10 embeds"}]


def test_query_params_and_wait_response(monkeypatch):
    from tools import discord_webhook

    captured = {}
    response_body = {"id": "42", "content": "Hello"}

    def fake_post(url, headers=None, params=None, json=None, timeout=None):
        captured.update({"params": params, "json": json})
        return _Response(status_code=200, body=response_body)

    monkeypatch.setattr(discord_webhook.httpx, "post", fake_post)

    messages = list(
        _tool()._invoke(
            {
                "webhook_url": "https://discord.com/api/webhooks/123/token",
                "content": "Hello",
                "wait": True,
                "thread_id": "987654321",
                "with_components": True,
                "allowed_mentions_json": '{"parse": []}',
            }
        )
    )

    assert captured["params"] == {
        "wait": "true",
        "thread_id": "987654321",
        "with_components": "true",
    }
    assert captured["json"]["allowed_mentions"] == {"parse": []}
    assert messages == [
        {"type": "text", "value": "Discord webhook message sent successfully"},
        {"type": "json", "value": response_body},
    ]


def test_components_v2_flags_reject_content():
    messages = list(
        _tool()._invoke(
            {
                "webhook_url": "https://discord.com/api/webhooks/123/token",
                "content": "This cannot be combined with IS_COMPONENTS_V2",
                "flags": 32768,
            }
        )
    )

    assert messages == [
        {
            "type": "text",
            "value": "Invalid message: IS_COMPONENTS_V2 flags cannot be combined with content, embeds_json, or poll_json",
        }
    ]

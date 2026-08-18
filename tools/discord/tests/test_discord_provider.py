import sys
from pathlib import Path

import httpx
import pytest
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from provider.discord import DiscordProvider


class _Response:
    def __init__(self, status_code):
        self.status_code = status_code


def _provider():
    return object.__new__(DiscordProvider)


def test_empty_token_does_not_call_discord(monkeypatch):
    from provider import discord

    monkeypatch.setattr(
        discord.httpx,
        "get",
        lambda *args, **kwargs: pytest.fail("Discord should not be called"),
    )
    _provider()._validate_credentials({})


def test_valid_token(monkeypatch):
    from provider import discord

    captured = {}

    def fake_get(url, headers=None, timeout=None):
        captured.update({"url": url, "headers": headers, "timeout": timeout})
        return _Response(200)

    monkeypatch.setattr(discord.httpx, "get", fake_get)
    _provider()._validate_credentials({"bot_token": " token "})
    assert captured["headers"] == {"Authorization": "Bot token"}


def test_invalid_token(monkeypatch):
    from provider import discord

    monkeypatch.setattr(discord.httpx, "get", lambda *args, **kwargs: _Response(401))
    with pytest.raises(ToolProviderCredentialValidationError):
        _provider()._validate_credentials({"bot_token": "bad"})


def test_validation_network_error(monkeypatch):
    from provider import discord

    def fail(*args, **kwargs):
        raise httpx.RequestError("offline")

    monkeypatch.setattr(discord.httpx, "get", fail)
    with pytest.raises(ToolProviderCredentialValidationError):
        _provider()._validate_credentials({"bot_token": "token"})

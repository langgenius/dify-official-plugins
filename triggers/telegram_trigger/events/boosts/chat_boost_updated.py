from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import TelegramUpdateEvent


class ChatBoostUpdatedEvent(TelegramUpdateEvent, Event):
    """Expose Telegram chat_boost updates."""

    update_key = "chat_boost"

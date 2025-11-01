from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import TelegramUpdateEvent


class ChatBoostRemovedEvent(TelegramUpdateEvent, Event):
    """Expose Telegram removed_chat_boost updates."""

    update_key = "removed_chat_boost"

from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import TelegramUpdateEvent


class ChatMemberUpdatedEvent(TelegramUpdateEvent, Event):
    """Expose Telegram chat member updates."""

    update_key = "chat_member"

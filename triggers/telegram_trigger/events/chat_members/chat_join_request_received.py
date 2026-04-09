from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import TelegramUpdateEvent


class ChatJoinRequestReceivedEvent(TelegramUpdateEvent, Event):
    """Expose Telegram chat join request updates."""

    update_key = "chat_join_request"

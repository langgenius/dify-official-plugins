from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import TelegramUpdateEvent


class MyChatMemberUpdatedEvent(TelegramUpdateEvent, Event):
    """Expose Telegram my chat member updates."""

    update_key = "my_chat_member"

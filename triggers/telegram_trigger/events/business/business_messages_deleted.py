from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import TelegramUpdateEvent


class BusinessMessagesDeletedEvent(TelegramUpdateEvent, Event):
    """Expose Telegram deleted business messages updates."""

    update_key = "deleted_business_messages"

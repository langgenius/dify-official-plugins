from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import TelegramUpdateEvent


class BusinessMessageReceivedEvent(TelegramUpdateEvent, Event):
    """Expose Telegram business message updates."""

    update_key = "business_message"

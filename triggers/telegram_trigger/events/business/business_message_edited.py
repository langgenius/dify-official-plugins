from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import TelegramUpdateEvent


class BusinessMessageEditedEvent(TelegramUpdateEvent, Event):
    """Expose Telegram edited business message updates."""

    update_key = "edited_business_message"

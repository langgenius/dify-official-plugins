from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import TelegramUpdateEvent


class BusinessConnectionUpdatedEvent(TelegramUpdateEvent, Event):
    """Expose Telegram business connection updates."""

    update_key = "business_connection"

from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import TelegramUpdateEvent


class MessageEditedEvent(TelegramUpdateEvent, Event):
    """Expose Telegram edited message updates."""

    update_key = "edited_message"

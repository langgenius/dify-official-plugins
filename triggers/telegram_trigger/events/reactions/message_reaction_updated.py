from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import TelegramUpdateEvent


class MessageReactionUpdatedEvent(TelegramUpdateEvent, Event):
    """Expose Telegram message reaction updates."""

    update_key = "message_reaction"

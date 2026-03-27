from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import TelegramUpdateEvent


class MessageReactionCountUpdatedEvent(TelegramUpdateEvent, Event):
    """Expose Telegram message reaction count updates."""

    update_key = "message_reaction_count"

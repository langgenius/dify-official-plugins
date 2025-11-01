from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import TelegramUpdateEvent


class InlineQueryReceivedEvent(TelegramUpdateEvent, Event):
    """Expose Telegram inline query updates."""

    update_key = "inline_query"

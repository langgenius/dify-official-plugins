from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import TelegramUpdateEvent


class CallbackQueryReceivedEvent(TelegramUpdateEvent, Event):
    """Expose Telegram callback query updates."""

    update_key = "callback_query"

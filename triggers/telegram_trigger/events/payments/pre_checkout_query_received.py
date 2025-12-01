from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import TelegramUpdateEvent


class PreCheckoutQueryReceivedEvent(TelegramUpdateEvent, Event):
    """Expose Telegram pre checkout query updates."""

    update_key = "pre_checkout_query"

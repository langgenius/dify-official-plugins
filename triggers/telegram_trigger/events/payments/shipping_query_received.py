from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import TelegramUpdateEvent


class ShippingQueryReceivedEvent(TelegramUpdateEvent, Event):
    """Expose Telegram shipping query updates."""

    update_key = "shipping_query"

from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import TelegramUpdateEvent


class InlineResultChosenEvent(TelegramUpdateEvent, Event):
    """Expose Telegram chosen inline result updates."""

    update_key = "chosen_inline_result"

from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import TelegramUpdateEvent


class PollStateUpdatedEvent(TelegramUpdateEvent, Event):
    """Expose Telegram poll updates."""

    update_key = "poll"

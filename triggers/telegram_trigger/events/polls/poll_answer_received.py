from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import TelegramUpdateEvent


class PollAnswerReceivedEvent(TelegramUpdateEvent, Event):
    """Expose Telegram poll answer updates."""

    update_key = "poll_answer"

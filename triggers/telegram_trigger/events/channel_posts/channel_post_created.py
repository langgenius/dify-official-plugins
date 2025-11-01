from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import TelegramUpdateEvent


class ChannelPostCreatedEvent(TelegramUpdateEvent, Event):
    """Expose Telegram channel post updates."""

    update_key = "channel_post"

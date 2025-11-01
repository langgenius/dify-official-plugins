from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import TelegramUpdateEvent


class ChannelPostEditedEvent(TelegramUpdateEvent, Event):
    """Expose Telegram edited channel post updates."""

    update_key = "edited_channel_post"

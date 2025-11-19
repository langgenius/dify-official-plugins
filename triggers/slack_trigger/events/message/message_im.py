from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class MessageImEvent(CatalogSlackEvent, Event):
    """Slack event handler for `message.im`."""

    EVENT_KEY = "message_im"

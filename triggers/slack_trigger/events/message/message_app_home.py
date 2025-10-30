from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class MessageAppHomeEvent(CatalogSlackEvent, Event):
    """Slack event handler for `message.app.home`."""

    EVENT_KEY = "message_app_home"

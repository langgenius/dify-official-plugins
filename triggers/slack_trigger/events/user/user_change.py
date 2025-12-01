from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class UserChangeEvent(CatalogSlackEvent, Event):
    """Slack event handler for `user.change`."""

    EVENT_KEY = "user_change"

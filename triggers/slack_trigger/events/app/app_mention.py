from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class AppMentionEvent(CatalogSlackEvent, Event):
    """Slack event handler for `app.mention`."""

    EVENT_KEY = "app_mention"

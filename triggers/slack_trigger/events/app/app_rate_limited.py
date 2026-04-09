from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class AppRateLimitedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `app.rate.limited`."""

    EVENT_KEY = "app_rate_limited"

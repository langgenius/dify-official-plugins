from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class AppUninstalledEvent(CatalogSlackEvent, Event):
    """Slack event handler for `app.uninstalled`."""

    EVENT_KEY = "app_uninstalled"

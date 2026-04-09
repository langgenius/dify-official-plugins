from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class ScopeDeniedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `scope.denied`."""

    EVENT_KEY = "scope_denied"

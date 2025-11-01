from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class ScopeGrantedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `scope.granted`."""

    EVENT_KEY = "scope_granted"

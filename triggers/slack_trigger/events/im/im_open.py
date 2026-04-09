from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class ImOpenEvent(CatalogSlackEvent, Event):
    """Slack event handler for `im.open`."""

    EVENT_KEY = "im_open"

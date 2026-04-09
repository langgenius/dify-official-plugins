from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class ImCloseEvent(CatalogSlackEvent, Event):
    """Slack event handler for `im.close`."""

    EVENT_KEY = "im_close"

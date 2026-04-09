from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class ImCreatedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `im.created`."""

    EVENT_KEY = "im_created"

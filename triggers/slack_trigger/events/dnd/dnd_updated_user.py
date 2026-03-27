from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class DndUpdatedUserEvent(CatalogSlackEvent, Event):
    """Slack event handler for `dnd.updated.user`."""

    EVENT_KEY = "dnd_updated_user"

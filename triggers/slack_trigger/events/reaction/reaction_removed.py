from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class ReactionRemovedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `reaction.removed`."""

    EVENT_KEY = "reaction_removed"

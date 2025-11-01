from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class ReactionAddedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `reaction.added`."""

    EVENT_KEY = "reaction_added"

from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class TokensRevokedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `tokens.revoked`."""

    EVENT_KEY = "tokens_revoked"

from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from .._catalog_event import CatalogSlackEvent


class EmailDomainChangedEvent(CatalogSlackEvent, Event):
    """Slack event handler for `email.domain.changed`."""

    EVENT_KEY = "email_domain_changed"

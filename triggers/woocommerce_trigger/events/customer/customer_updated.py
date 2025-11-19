from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import WooCommerceBaseEvent


class CustomerUpdatedEvent(WooCommerceBaseEvent, Event):
    """Triggered when WooCommerce sends the customer.updated topic."""

    resource_property = "customer"

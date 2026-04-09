from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import WooCommerceBaseEvent


class CustomerCreatedEvent(WooCommerceBaseEvent, Event):
    """Triggered when WooCommerce sends the customer.created topic."""

    resource_property = "customer"

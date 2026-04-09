from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import WooCommerceBaseEvent


class CustomerDeletedEvent(WooCommerceBaseEvent, Event):
    """Triggered when WooCommerce sends the customer.deleted topic."""

    resource_property = "customer"

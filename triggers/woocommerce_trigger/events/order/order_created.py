from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import WooCommerceBaseEvent


class OrderCreatedEvent(WooCommerceBaseEvent, Event):
    """Triggered when WooCommerce sends the order.created topic."""

    resource_property = "order"

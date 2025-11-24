from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import WooCommerceBaseEvent


class OrderUpdatedEvent(WooCommerceBaseEvent, Event):
    """Triggered when WooCommerce sends the order.updated topic."""

    resource_property = "order"

from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import WooCommerceBaseEvent


class OrderDeletedEvent(WooCommerceBaseEvent, Event):
    """Triggered when WooCommerce sends the order.deleted topic."""

    resource_property = "order"

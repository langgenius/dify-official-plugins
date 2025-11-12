from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import WooCommerceBaseEvent


class ProductCreatedEvent(WooCommerceBaseEvent, Event):
    """Triggered when WooCommerce sends the product.created topic."""

    resource_property = "product"

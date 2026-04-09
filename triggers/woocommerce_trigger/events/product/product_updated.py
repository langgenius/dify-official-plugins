from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import WooCommerceBaseEvent


class ProductUpdatedEvent(WooCommerceBaseEvent, Event):
    """Triggered when WooCommerce sends the product.updated topic."""

    resource_property = "product"

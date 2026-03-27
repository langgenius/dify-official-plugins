from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import WooCommerceBaseEvent


class ProductDeletedEvent(WooCommerceBaseEvent, Event):
    """Triggered when WooCommerce sends the product.deleted topic."""

    resource_property = "product"

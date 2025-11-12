from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import WooCommerceBaseEvent


class CouponCreatedEvent(WooCommerceBaseEvent, Event):
    """Triggered when WooCommerce sends the coupon.created topic."""

    resource_property = "coupon"

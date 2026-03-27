from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import WooCommerceBaseEvent


class CouponUpdatedEvent(WooCommerceBaseEvent, Event):
    """Triggered when WooCommerce sends the coupon.updated topic."""

    resource_property = "coupon"

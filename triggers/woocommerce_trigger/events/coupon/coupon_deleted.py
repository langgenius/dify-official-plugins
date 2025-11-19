from __future__ import annotations

from dify_plugin.interfaces.trigger import Event

from ..base import WooCommerceBaseEvent


class CouponDeletedEvent(WooCommerceBaseEvent, Event):
    """Triggered when WooCommerce sends the coupon.deleted topic."""

    resource_property = "coupon"

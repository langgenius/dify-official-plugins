from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables


class WooCommerceBaseEvent:
    """Return the raw WooCommerce payload and webhook headers."""

    resource_property: str = "resource"

    def _on_event(self, request: Request, parameters: Mapping[str, Any], payload: Mapping[str, Any]) -> Variables:
        data = payload or self._force_json(request)
        webhook_headers = self._collect_headers(request)
        variables = {self.resource_property: data, "webhook": webhook_headers}
        return Variables(variables=variables)

    @staticmethod
    def _force_json(request: Request) -> Mapping[str, Any]:
        parsed = request.get_json(force=True)  # type: ignore[no-any-return]
        if not isinstance(parsed, Mapping):
            raise ValueError("WooCommerce event payload must be a JSON object")
        return parsed

    @staticmethod
    def _collect_headers(request: Request) -> dict[str, Any]:
        return {
            "id": request.headers.get("X-WC-Webhook-ID"),
            "delivery_id": request.headers.get("X-WC-Webhook-Delivery-ID"),
            "resource": request.headers.get("X-WC-Webhook-Resource"),
            "event": request.headers.get("X-WC-Webhook-Event"),
            "topic": request.headers.get("X-WC-Webhook-Topic"),
            "source": request.headers.get("X-WC-Webhook-Source"),
        }

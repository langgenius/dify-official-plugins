from collections.abc import Mapping
from typing import Any

from werkzeug import Request

from dify_plugin.entities.trigger import Variables
from dify_plugin.errors.trigger import EventIgnoreError
from dify_plugin.interfaces.trigger import Event


class CustomerRemovedEvent(Event):
    """Linear customer removed webhook event."""

    @staticmethod
    def _parse_list(value: str | None) -> list[str]:
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    def _check_name_contains(self, data: Mapping[str, Any], name_contains: str | None) -> None:
        keywords = [keyword.lower() for keyword in self._parse_list(name_contains)]
        if not keywords:
            return

        name = (data.get("name") or "").lower()
        if not any(keyword in name for keyword in keywords):
            raise EventIgnoreError()

    def _check_status_filter(self, data: Mapping[str, Any], status_filter: str | None) -> None:
        allowed_statuses = [value.lower() for value in self._parse_list(status_filter)]
        if not allowed_statuses:
            return

        status = data.get("status") or {}
        status_name = (status.get("name") or status.get("displayName") or "").lower()
        status_id = (data.get("statusId") or "").lower()
        if status_id in allowed_statuses or status_name in allowed_statuses:
            return

        raise EventIgnoreError()

    def _check_tier_filter(self, data: Mapping[str, Any], tier_filter: str | None) -> None:
        allowed_tiers = [value.lower() for value in self._parse_list(tier_filter)]
        if not allowed_tiers:
            return

        tier = data.get("tier") or {}
        tier_name = (tier.get("name") or tier.get("displayName") or "").lower()
        tier_id = (data.get("tierId") or "").lower()
        if tier_id in allowed_tiers or tier_name in allowed_tiers:
            return

        raise EventIgnoreError()

    def _check_owner_filter(self, data: Mapping[str, Any], owner_filter: str | None) -> None:
        allowed_owner_ids = self._parse_list(owner_filter)
        if not allowed_owner_ids:
            return

        owner_id = (data.get("ownerId") or "").strip()
        if not owner_id or owner_id not in allowed_owner_ids:
            raise EventIgnoreError()

    def _check_domain_filter(self, data: Mapping[str, Any], domain_filter: str | None) -> None:
        keywords = [keyword.lower() for keyword in self._parse_list(domain_filter)]
        if not keywords:
            return

        domains = data.get("domains") or []
        normalized_domains = [domain.lower() for domain in domains if isinstance(domain, str)]
        if not any(any(keyword in domain for keyword in keywords) for domain in normalized_domains):
            raise EventIgnoreError()

    def _apply_filters(self, data: Mapping[str, Any], parameters: Mapping[str, Any]) -> None:
        self._check_name_contains(data, parameters.get("name_contains"))
        self._check_status_filter(data, parameters.get("status_filter"))
        self._check_tier_filter(data, parameters.get("tier_filter"))
        self._check_owner_filter(data, parameters.get("owner_filter"))
        self._check_domain_filter(data, parameters.get("domain_contains"))

    def _on_event(self, request: Request, parameters: Mapping[str, Any]) -> Variables:
        payload = request.get_json()
        if not payload:
            raise ValueError("No payload received")

        customer_data = payload.get("data")
        if not customer_data:
            raise ValueError("No customer data in payload")

        self._apply_filters(customer_data, parameters)
        return Variables(variables={**payload})

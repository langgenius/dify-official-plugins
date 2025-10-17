import copy

import pytest

from events.customer.customer_created import CustomerCreatedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestCustomerCreatedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "create",
            "type": "Customer",
            "data": {
                "id": "customer-123",
                "name": "Acme Corporation",
                "domains": ["acme.com", "acme.io"],
                "ownerId": "user-owner",
                "statusId": "status-active",
                "status": {"id": "status-active", "name": "active", "displayName": "Active"},
                "tierId": "tier-enterprise",
                "tier": {"id": "tier-enterprise", "name": "enterprise", "displayName": "Enterprise"},
                "revenue": 4500000,
                "size": 900,
                "slackChannelId": "C123456",
                "approximateNeedCount": 12,
                "createdAt": "2025-10-16T12:00:00.000Z",
                "updatedAt": "2025-10-16T12:00:00.000Z",
                "archivedAt": None,
                "url": "https://linear.app/workspace/customer/customer-123",
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = CustomerCreatedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "create"
        assert result.variables["data"]["name"] == "Acme Corporation"

    def test_name_filter(self):
        event = CustomerCreatedEvent(self.runtime)
        params = {"name_contains": "acme,corp"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "customer-123"

    def test_name_filter_no_match(self):
        event = CustomerCreatedEvent(self.runtime)
        params = {"name_contains": "beta"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_status_filter_by_name(self):
        event = CustomerCreatedEvent(self.runtime)
        params = {"status_filter": "active"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["status"]["name"] == "active"

    def test_status_filter_by_id(self):
        event = CustomerCreatedEvent(self.runtime)
        params = {"status_filter": "status-active"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["statusId"] == "status-active"

    def test_status_filter_no_match(self):
        event = CustomerCreatedEvent(self.runtime)
        params = {"status_filter": "status-inactive"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_tier_filter(self):
        event = CustomerCreatedEvent(self.runtime)
        params = {"tier_filter": "enterprise"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["tier"]["name"] == "enterprise"

    def test_tier_filter_no_match(self):
        event = CustomerCreatedEvent(self.runtime)
        params = {"tier_filter": "starter"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_owner_filter(self):
        event = CustomerCreatedEvent(self.runtime)
        params = {"owner_filter": "user-owner,user-other"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["ownerId"] == "user-owner"

    def test_owner_filter_no_match(self):
        event = CustomerCreatedEvent(self.runtime)
        params = {"owner_filter": "user-other"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_domain_filter(self):
        event = CustomerCreatedEvent(self.runtime)
        params = {"domain_contains": "acme"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert "acme.com" in result.variables["data"]["domains"]

    def test_domain_filter_no_match(self):
        event = CustomerCreatedEvent(self.runtime)
        params = {"domain_contains": "contoso"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_missing_payload(self):
        event = CustomerCreatedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

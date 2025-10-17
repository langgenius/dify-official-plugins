import copy

import pytest

from events.customer.customer_removed import CustomerRemovedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestCustomerRemovedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "remove",
            "type": "Customer",
            "data": {
                "id": "customer-789",
                "name": "Legacy Co",
                "domains": ["legacy.co", "legacy-app.com"],
                "ownerId": "user-legacy",
                "statusId": "status-inactive",
                "status": {"id": "status-inactive", "name": "inactive", "displayName": "Inactive"},
                "tierId": "tier-basic",
                "tier": {"id": "tier-basic", "name": "basic", "displayName": "Basic"},
                "revenue": 150000,
                "size": 50,
                "slackChannelId": None,
                "approximateNeedCount": 0,
                "createdAt": "2024-03-01T12:00:00.000Z",
                "updatedAt": "2025-05-01T12:00:00.000Z",
                "archivedAt": "2025-05-01T12:00:00.000Z",
                "url": "https://linear.app/workspace/customer/customer-789",
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = CustomerRemovedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "remove"
        assert result.variables["data"]["status"]["name"] == "inactive"

    def test_name_filter(self):
        event = CustomerRemovedEvent(self.runtime)
        params = {"name_contains": "legacy"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "customer-789"

    def test_name_filter_no_match(self):
        event = CustomerRemovedEvent(self.runtime)
        params = {"name_contains": "acme"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_status_filter(self):
        event = CustomerRemovedEvent(self.runtime)
        params = {"status_filter": "inactive"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["status"]["name"] == "inactive"

    def test_status_filter_no_match(self):
        event = CustomerRemovedEvent(self.runtime)
        params = {"status_filter": "active"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_tier_filter(self):
        event = CustomerRemovedEvent(self.runtime)
        params = {"tier_filter": "tier-basic"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["tierId"] == "tier-basic"

    def test_tier_filter_no_match(self):
        event = CustomerRemovedEvent(self.runtime)
        params = {"tier_filter": "tier-enterprise"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_owner_filter(self):
        event = CustomerRemovedEvent(self.runtime)
        params = {"owner_filter": "user-legacy"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["ownerId"] == "user-legacy"

    def test_owner_filter_no_match(self):
        event = CustomerRemovedEvent(self.runtime)
        params = {"owner_filter": "user-new"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_domain_filter(self):
        event = CustomerRemovedEvent(self.runtime)
        params = {"domain_contains": "legacy"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert any(domain.startswith("legacy") for domain in result.variables["data"]["domains"])

    def test_domain_filter_no_match(self):
        event = CustomerRemovedEvent(self.runtime)
        params = {"domain_contains": "acme"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_missing_payload(self):
        event = CustomerRemovedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

import copy

import pytest

from events.customer.customer_updated import CustomerUpdatedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestCustomerUpdatedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "update",
            "type": "Customer",
            "data": {
                "id": "customer-456",
                "name": "Acme Corporation",
                "domains": ["acme.com", "mobile.acme.io"],
                "ownerId": "user-owner",
                "statusId": "status-at-risk",
                "status": {"id": "status-at-risk", "name": "at_risk", "displayName": "At Risk"},
                "tierId": "tier-gold",
                "tier": {"id": "tier-gold", "name": "gold", "displayName": "Gold"},
                "revenue": 5000000,
                "size": 1200,
                "slackChannelId": "C234567",
                "approximateNeedCount": 18,
                "createdAt": "2025-10-01T12:00:00.000Z",
                "updatedAt": "2025-11-01T12:00:00.000Z",
                "archivedAt": None,
                "url": "https://linear.app/workspace/customer/customer-456",
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = CustomerUpdatedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "update"
        assert result.variables["data"]["status"]["name"] == "at_risk"

    def test_name_filter(self):
        event = CustomerUpdatedEvent(self.runtime)
        params = {"name_contains": "acme"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "customer-456"

    def test_name_filter_no_match(self):
        event = CustomerUpdatedEvent(self.runtime)
        params = {"name_contains": "beta"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_status_filter(self):
        event = CustomerUpdatedEvent(self.runtime)
        params = {"status_filter": "status-at-risk"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["statusId"] == "status-at-risk"

    def test_status_filter_no_match(self):
        event = CustomerUpdatedEvent(self.runtime)
        params = {"status_filter": "status-active"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_tier_filter(self):
        event = CustomerUpdatedEvent(self.runtime)
        params = {"tier_filter": "gold"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["tier"]["name"] == "gold"

    def test_tier_filter_no_match(self):
        event = CustomerUpdatedEvent(self.runtime)
        params = {"tier_filter": "silver"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_owner_filter(self):
        event = CustomerUpdatedEvent(self.runtime)
        params = {"owner_filter": "user-owner"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["ownerId"] == "user-owner"

    def test_owner_filter_no_match(self):
        event = CustomerUpdatedEvent(self.runtime)
        params = {"owner_filter": "user-other"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_domain_filter(self):
        event = CustomerUpdatedEvent(self.runtime)
        params = {"domain_contains": "mobile"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert any(domain.endswith("mobile.acme.io") for domain in result.variables["data"]["domains"])

    def test_domain_filter_no_match(self):
        event = CustomerUpdatedEvent(self.runtime)
        params = {"domain_contains": "contoso"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_missing_payload(self):
        event = CustomerUpdatedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

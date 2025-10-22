import copy

import pytest

from events.customer_need.customer_need_updated import CustomerNeedUpdatedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestCustomerNeedUpdatedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "update",
            "type": "CustomerNeed",
            "data": {
                "id": "need-456",
                "body": "Need timeframe updated to align with Q1 goals.",
                "priority": 1,
                "customerId": "customer-123",
                "issueId": "issue-999",
                "projectId": "project-222",
                "creatorId": "user-creator",
                "createdAt": "2025-10-16T12:00:00.000Z",
                "updatedAt": "2025-10-20T12:00:00.000Z",
                "archivedAt": None,
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = CustomerNeedUpdatedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "update"
        assert result.variables["data"]["priority"] == 1

    def test_body_filter(self):
        event = CustomerNeedUpdatedEvent(self.runtime)
        params = {"body_contains": "q1"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "need-456"

    def test_body_filter_no_match(self):
        event = CustomerNeedUpdatedEvent(self.runtime)
        params = {"body_contains": "dark"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_priority_filter(self):
        event = CustomerNeedUpdatedEvent(self.runtime)
        params = {"priority_filter": "1"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["priority"] == 1

    def test_priority_filter_no_match(self):
        event = CustomerNeedUpdatedEvent(self.runtime)
        params = {"priority_filter": "2"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_customer_filter(self):
        event = CustomerNeedUpdatedEvent(self.runtime)
        params = {"customer_filter": "customer-123"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["customerId"] == "customer-123"

    def test_issue_filter(self):
        event = CustomerNeedUpdatedEvent(self.runtime)
        params = {"issue_filter": "issue-999"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["issueId"] == "issue-999"

    def test_project_filter(self):
        event = CustomerNeedUpdatedEvent(self.runtime)
        params = {"project_filter": "project-222"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["projectId"] == "project-222"

    def test_creator_filter(self):
        event = CustomerNeedUpdatedEvent(self.runtime)
        params = {"creator_filter": "user-creator"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["creatorId"] == "user-creator"

    def test_filters_combined(self):
        event = CustomerNeedUpdatedEvent(self.runtime)
        params = {
            "body_contains": "q1",
            "priority_filter": "1",
            "customer_filter": "customer-123",
        }

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "need-456"

    def test_missing_payload(self):
        event = CustomerNeedUpdatedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

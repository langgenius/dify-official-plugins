import copy

import pytest

from events.customer_need.customer_need_created import CustomerNeedCreatedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestCustomerNeedCreatedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "create",
            "type": "CustomerNeed",
            "data": {
                "id": "need-123",
                "body": "Customer requests dark mode support.",
                "priority": 2,
                "customerId": "customer-123",
                "issueId": "issue-888",
                "projectId": "project-222",
                "creatorId": "user-creator",
                "createdAt": "2025-10-16T12:00:00.000Z",
                "updatedAt": "2025-10-16T12:00:00.000Z",
                "archivedAt": None,
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = CustomerNeedCreatedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "create"
        assert result.variables["data"]["priority"] == 2

    def test_body_filter(self):
        event = CustomerNeedCreatedEvent(self.runtime)
        params = {"body_contains": "dark,mode"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "need-123"

    def test_body_filter_no_match(self):
        event = CustomerNeedCreatedEvent(self.runtime)
        params = {"body_contains": "analytics"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_priority_filter(self):
        event = CustomerNeedCreatedEvent(self.runtime)
        params = {"priority_filter": "1,2"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["priority"] == 2

    def test_priority_filter_no_match(self):
        event = CustomerNeedCreatedEvent(self.runtime)
        params = {"priority_filter": "3,4"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_customer_filter(self):
        event = CustomerNeedCreatedEvent(self.runtime)
        params = {"customer_filter": "customer-123"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["customerId"] == "customer-123"

    def test_customer_filter_no_match(self):
        event = CustomerNeedCreatedEvent(self.runtime)
        params = {"customer_filter": "customer-999"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_issue_filter(self):
        event = CustomerNeedCreatedEvent(self.runtime)
        params = {"issue_filter": "issue-888"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["issueId"] == "issue-888"

    def test_issue_filter_no_match(self):
        event = CustomerNeedCreatedEvent(self.runtime)
        params = {"issue_filter": "issue-999"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_project_filter(self):
        event = CustomerNeedCreatedEvent(self.runtime)
        params = {"project_filter": "project-222"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["projectId"] == "project-222"

    def test_project_filter_no_match(self):
        event = CustomerNeedCreatedEvent(self.runtime)
        params = {"project_filter": "project-999"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_creator_filter(self):
        event = CustomerNeedCreatedEvent(self.runtime)
        params = {"creator_filter": "user-creator"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["creatorId"] == "user-creator"

    def test_creator_filter_no_match(self):
        event = CustomerNeedCreatedEvent(self.runtime)
        params = {"creator_filter": "user-other"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_missing_payload(self):
        event = CustomerNeedCreatedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

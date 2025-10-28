import copy

import pytest

from events.customer_need.customer_need_removed import CustomerNeedRemovedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestCustomerNeedRemovedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "remove",
            "type": "CustomerNeed",
            "data": {
                "id": "need-789",
                "body": "Legacy feature request was resolved and archived.",
                "priority": 3,
                "customerId": "customer-456",
                "issueId": "issue-1001",
                "projectId": "project-555",
                "creatorId": "user-legacy",
                "createdAt": "2025-09-01T12:00:00.000Z",
                "updatedAt": "2025-10-01T12:00:00.000Z",
                "archivedAt": "2025-10-01T12:00:00.000Z",
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = CustomerNeedRemovedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "remove"
        assert result.variables["data"]["priority"] == 3

    def test_body_filter(self):
        event = CustomerNeedRemovedEvent(self.runtime)
        params = {"body_contains": "archived"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "need-789"

    def test_priority_filter(self):
        event = CustomerNeedRemovedEvent(self.runtime)
        params = {"priority_filter": "3"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["priority"] == 3

    def test_customer_filter(self):
        event = CustomerNeedRemovedEvent(self.runtime)
        params = {"customer_filter": "customer-456"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["customerId"] == "customer-456"

    def test_issue_filter(self):
        event = CustomerNeedRemovedEvent(self.runtime)
        params = {"issue_filter": "issue-1001"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["issueId"] == "issue-1001"

    def test_project_filter(self):
        event = CustomerNeedRemovedEvent(self.runtime)
        params = {"project_filter": "project-555"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["projectId"] == "project-555"

    def test_creator_filter(self):
        event = CustomerNeedRemovedEvent(self.runtime)
        params = {"creator_filter": "user-legacy"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["creatorId"] == "user-legacy"

    def test_filter_no_match(self):
        event = CustomerNeedRemovedEvent(self.runtime)
        params = {"priority_filter": "1"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_missing_payload(self):
        event = CustomerNeedRemovedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

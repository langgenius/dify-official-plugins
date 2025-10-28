import json
import pytest

from events.issue.issue_updated import IssueUpdatedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    """Mock Request object for testing"""
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    """Mock Runtime object for testing"""
    pass


class TestIssueUpdatedEvent:
    """Test suite for IssueUpdatedEvent"""

    def setup_method(self):
        """Set up test fixtures"""
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "update",
            "type": "Issue",
            "data": {
                "id": "issue-123",
                "identifier": "TEST-123",
                "number": 123,
                "title": "Test Issue Updated",
                "description": "Test description",
                "priority": 2,
                "priorityLabel": "High",
                "url": "https://linear.app/test/issue/TEST-123",
                "state": {
                    "id": "state-123",
                    "name": "In Progress",
                    "type": "started"
                },
                "assignee": {
                    "id": "user-123",
                    "name": "Test User",
                    "email": "test@example.com"
                },
                "assigneeId": "user-123",
                "teamId": "team-123",
                "updatedAt": "2025-10-16T12:00:00.000Z"
            },
            "actor": {
                "id": "user-456",
                "name": "Actor User"
            }
        }

    def test_basic_event_handling(self):
        """Test basic event handling without filters"""
        event = IssueUpdatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        result = event._on_event(request, {}, request.get_json())

        assert result.variables["action"] == "update"
        assert result.variables["type"] == "Issue"
        assert result.variables["data"]["identifier"] == "TEST-123"

    def test_priority_filter_match(self):
        """Test priority filter with matching priority"""
        event = IssueUpdatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {"priority_filter": "1,2,3"}

        result = event._on_event(request, parameters, request.get_json())
        assert result.variables["data"]["priority"] == 2

    def test_priority_filter_no_match(self):
        """Test priority filter with non-matching priority"""
        event = IssueUpdatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {"priority_filter": "0,1"}  # Priority 0 and 1 only

        with pytest.raises(EventIgnoreError):
            event._on_event(request, parameters, request.get_json())

    def test_state_filter_match(self):
        """Test state filter with matching state"""
        event = IssueUpdatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {"state_filter": "in progress,backlog"}

        result = event._on_event(request, parameters, request.get_json())
        assert result.variables["data"]["state"]["name"] == "In Progress"

    def test_state_filter_no_match(self):
        """Test state filter with non-matching state"""
        event = IssueUpdatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {"state_filter": "done,canceled"}

        with pytest.raises(EventIgnoreError):
            event._on_event(request, parameters, request.get_json())

    def test_title_contains_match(self):
        """Test title filter with matching keyword"""
        event = IssueUpdatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {"title_contains": "test,bug,feature"}

        result = event._on_event(request, parameters, request.get_json())
        assert "test" in result.variables["data"]["title"].lower()

    def test_title_contains_no_match(self):
        """Test title filter with non-matching keyword"""
        event = IssueUpdatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {"title_contains": "urgent,critical"}

        with pytest.raises(EventIgnoreError):
            event._on_event(request, parameters, request.get_json())

    def test_multiple_filters_all_match(self):
        """Test multiple filters when all match"""
        event = IssueUpdatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {
            "priority_filter": "2,3",
            "state_filter": "in progress",
            "title_contains": "test"
        }

        result = event._on_event(request, parameters, request.get_json())
        assert result.variables["data"]["identifier"] == "TEST-123"

    def test_multiple_filters_one_fails(self):
        """Test multiple filters when one doesn't match"""
        event = IssueUpdatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {
            "priority_filter": "2,3",  # Matches
            "state_filter": "done",     # Doesn't match
            "title_contains": "test"    # Matches
        }

        with pytest.raises(EventIgnoreError):
            event._on_event(request, parameters, request.get_json())

    def test_empty_filters(self):
        """Test that empty filters don't block events"""
        event = IssueUpdatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {
            "priority_filter": "",
            "state_filter": "",
            "title_contains": ""
        }

        result = event._on_event(request, parameters, request.get_json())
        assert result.variables["data"]["identifier"] == "TEST-123"

    def test_missing_payload(self):
        """Test handling of missing payload"""
        event = IssueUpdatedEvent(self.runtime)
        request = MockRequest(None)

        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(request, {}, request.get_json())

    def test_missing_data_field(self):
        """Test handling of missing data field"""
        event = IssueUpdatedEvent(self.runtime)
        request = MockRequest({"action": "update", "type": "Issue"})

        with pytest.raises(ValueError, match="No issue data in payload"):
            event._on_event(request, {}, request.get_json())

    def test_state_case_insensitive(self):
        """Test that state filter is case-insensitive"""
        event = IssueUpdatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {"state_filter": "IN PROGRESS,DONE"}

        result = event._on_event(request, parameters, request.get_json())
        assert result.variables["data"]["state"]["name"] == "In Progress"

    def test_title_case_insensitive(self):
        """Test that title filter is case-insensitive"""
        event = IssueUpdatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {"title_contains": "TEST"}

        result = event._on_event(request, parameters, request.get_json())
        assert result.variables["data"]["title"] == "Test Issue Updated"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

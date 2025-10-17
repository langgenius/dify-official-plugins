import pytest

from events.issue.issue_removed import IssueRemovedEvent
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


class TestIssueRemovedEvent:
    """Test suite for IssueRemovedEvent"""

    def setup_method(self):
        """Set up test fixtures"""
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "remove",
            "type": "Issue",
            "data": {
                "id": "issue-123",
                "identifier": "TEST-123",
                "number": 123,
                "title": "Test Issue Removed",
                "description": "Test description",
                "priority": 2,
                "priorityLabel": "High",
                "url": "https://linear.app/test/issue/TEST-123",
                "archivedAt": "2025-10-16T12:00:00.000Z",
                "teamId": "team-123"
            },
            "actor": {
                "id": "user-456",
                "name": "Actor User"
            }
        }

    def test_basic_event_handling(self):
        """Test basic event handling without filters"""
        event = IssueRemovedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        result = event._on_event(request, {})

        assert result.variables["action"] == "remove"
        assert result.variables["type"] == "Issue"
        assert result.variables["data"]["identifier"] == "TEST-123"

    def test_title_contains_match(self):
        """Test title filter with matching keyword"""
        event = IssueRemovedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {"title_contains": "test,bug,feature"}

        result = event._on_event(request, parameters)
        assert "test" in result.variables["data"]["title"].lower()

    def test_title_contains_no_match(self):
        """Test title filter with non-matching keyword"""
        event = IssueRemovedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {"title_contains": "urgent,critical"}

        with pytest.raises(EventIgnoreError):
            event._on_event(request, parameters)

    def test_empty_filter(self):
        """Test that empty filter doesn't block events"""
        event = IssueRemovedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {"title_contains": ""}

        result = event._on_event(request, parameters)
        assert result.variables["data"]["identifier"] == "TEST-123"

    def test_missing_payload(self):
        """Test handling of missing payload"""
        event = IssueRemovedEvent(self.runtime)
        request = MockRequest(None)

        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(request, {})

    def test_missing_data_field(self):
        """Test handling of missing data field"""
        event = IssueRemovedEvent(self.runtime)
        request = MockRequest({"action": "remove", "type": "Issue"})

        with pytest.raises(ValueError, match="No issue data in payload"):
            event._on_event(request, {})

    def test_title_case_insensitive(self):
        """Test that title filter is case-insensitive"""
        event = IssueRemovedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {"title_contains": "TEST"}

        result = event._on_event(request, parameters)
        assert result.variables["data"]["title"] == "Test Issue Removed"

    def test_archived_at_present(self):
        """Test that archivedAt is included in the response"""
        event = IssueRemovedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        result = event._on_event(request, {})

        assert "archivedAt" in result.variables["data"]
        assert result.variables["data"]["archivedAt"] == "2025-10-16T12:00:00.000Z"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

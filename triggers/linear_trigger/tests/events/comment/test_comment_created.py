import pytest

from events.comment.comment_created import CommentCreatedEvent
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


class TestCommentCreatedEvent:
    """Test suite for CommentCreatedEvent"""

    def setup_method(self):
        """Set up test fixtures"""
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "create",
            "type": "Comment",
            "data": {
                "id": "comment-123",
                "body": "This is a test comment with bug keyword",
                "createdAt": "2025-10-16T12:00:00.000Z",
                "updatedAt": "2025-10-16T12:00:00.000Z",
                "user": {
                    "id": "user-123",
                    "name": "Test User",
                    "email": "test@example.com"
                },
                "userId": "user-123",
                "issue": {
                    "id": "issue-123",
                    "identifier": "TEST-123",
                    "title": "Test Issue"
                },
                "issueId": "issue-123"
            },
            "actor": {
                "id": "user-123",
                "name": "Test User"
            }
        }

    def test_basic_event_handling(self):
        """Test basic event handling without filters"""
        event = CommentCreatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        result = event._on_event(request, {})

        assert result.variables["action"] == "create"
        assert result.variables["type"] == "Comment"
        assert result.variables["data"]["id"] == "comment-123"

    def test_body_contains_match(self):
        """Test body filter with matching keyword"""
        event = CommentCreatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {"body_contains": "bug,feature,urgent"}

        result = event._on_event(request, parameters)
        assert "bug" in result.variables["data"]["body"].lower()

    def test_body_contains_no_match(self):
        """Test body filter with non-matching keyword"""
        event = CommentCreatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {"body_contains": "urgent,critical,blocker"}

        with pytest.raises(EventIgnoreError):
            event._on_event(request, parameters)

    def test_issue_only_filter_with_issue_comment(self):
        """Test issue_only filter with comment on issue"""
        event = CommentCreatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {"issue_only": True}

        result = event._on_event(request, parameters)
        assert result.variables["data"]["issueId"] == "issue-123"

    def test_issue_only_filter_without_issue(self):
        """Test issue_only filter with comment not on issue"""
        event = CommentCreatedEvent(self.runtime)
        # Create payload without issueId (e.g., comment on project update)
        payload = {
            "action": "create",
            "type": "Comment",
            "data": {
                "id": "comment-456",
                "body": "Comment on project update",
                "projectUpdateId": "project-update-123",
                "userId": "user-123"
            },
            "actor": {"id": "user-123"}
        }
        request = MockRequest(payload)
        parameters = {"issue_only": True}

        with pytest.raises(EventIgnoreError):
            event._on_event(request, parameters)

    def test_multiple_filters_all_match(self):
        """Test multiple filters when all match"""
        event = CommentCreatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {
            "body_contains": "bug,test",
            "issue_only": True
        }

        result = event._on_event(request, parameters)
        assert result.variables["data"]["id"] == "comment-123"

    def test_multiple_filters_one_fails(self):
        """Test multiple filters when one doesn't match"""
        event = CommentCreatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {
            "body_contains": "urgent",  # Doesn't match
            "issue_only": True           # Matches
        }

        with pytest.raises(EventIgnoreError):
            event._on_event(request, parameters)

    def test_empty_filters(self):
        """Test that empty filters don't block events"""
        event = CommentCreatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {
            "body_contains": "",
            "issue_only": False
        }

        result = event._on_event(request, parameters)
        assert result.variables["data"]["id"] == "comment-123"

    def test_missing_payload(self):
        """Test handling of missing payload"""
        event = CommentCreatedEvent(self.runtime)
        request = MockRequest(None)

        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(request, {})

    def test_missing_data_field(self):
        """Test handling of missing data field"""
        event = CommentCreatedEvent(self.runtime)
        request = MockRequest({"action": "create", "type": "Comment"})

        with pytest.raises(ValueError, match="No comment data in payload"):
            event._on_event(request, {})

    def test_body_case_insensitive(self):
        """Test that body filter is case-insensitive"""
        event = CommentCreatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {"body_contains": "BUG"}

        result = event._on_event(request, parameters)
        assert result.variables["data"]["body"].lower().find("bug") >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

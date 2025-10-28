import copy

import pytest

from events.attachment.attachment_removed import AttachmentRemovedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestAttachmentRemovedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "remove",
            "type": "Attachment",
            "data": {
                "id": "att-123",
                "title": "Design Spec v3",
                "subtitle": "Archived draft",
                "url": "https://linear.app/attachments/att-123",
                "issueId": "ISSUE-1",
                "originalIssueId": "ISSUE-1",
                "creatorId": "user-1",
                "externalUserCreatorId": None,
                "sourceType": "github",
                "groupBySource": False,
                "metadata": {"branch": "feature/login"},
                "createdAt": "2025-10-16T12:00:00.000Z",
                "updatedAt": "2025-10-16T13:00:00.000Z",
                "archivedAt": "2025-10-20T09:00:00.000Z",
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = AttachmentRemovedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "remove"
        assert result.variables["data"]["archivedAt"] == "2025-10-20T09:00:00.000Z"

    def test_title_filter_match(self):
        event = AttachmentRemovedEvent(self.runtime)
        params = {"title_contains": "design"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "att-123"

    def test_title_filter_no_match(self):
        event = AttachmentRemovedEvent(self.runtime)
        params = {"title_contains": "retro"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_source_type_filter_match(self):
        event = AttachmentRemovedEvent(self.runtime)
        params = {"source_type_filter": "github"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["sourceType"] == "github"

    def test_source_type_filter_no_match(self):
        event = AttachmentRemovedEvent(self.runtime)
        params = {"source_type_filter": "slack"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_issue_filter_match(self):
        event = AttachmentRemovedEvent(self.runtime)
        params = {"issue_filter": "ISSUE-1"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["issueId"] == "ISSUE-1"

    def test_issue_filter_no_match(self):
        event = AttachmentRemovedEvent(self.runtime)
        params = {"issue_filter": "ISSUE-9"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_multiple_filters_all_match(self):
        event = AttachmentRemovedEvent(self.runtime)
        params = {
            "title_contains": "design",
            "source_type_filter": "github",
            "issue_filter": "ISSUE-1",
        }

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "att-123"

    def test_missing_payload(self):
        event = AttachmentRemovedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

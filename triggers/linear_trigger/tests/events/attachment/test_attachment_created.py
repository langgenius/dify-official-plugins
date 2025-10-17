import copy

import pytest

from events.attachment.attachment_created import AttachmentCreatedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestAttachmentCreatedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "create",
            "type": "Attachment",
            "data": {
                "id": "att-123",
                "title": "Design Spec v2",
                "subtitle": "Latest draft",
                "url": "https://linear.app/attachments/att-123",
                "issueId": "ISSUE-1",
                "originalIssueId": "ISSUE-1",
                "creatorId": "user-1",
                "externalUserCreatorId": None,
                "sourceType": "github",
                "groupBySource": True,
                "metadata": {"branch": "feature/login"},
                "createdAt": "2025-10-16T12:00:00.000Z",
                "updatedAt": "2025-10-16T12:01:00.000Z",
                "archivedAt": None,
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = AttachmentCreatedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "create"
        assert result.variables["data"]["sourceType"] == "github"

    def test_title_filter_match(self):
        event = AttachmentCreatedEvent(self.runtime)
        params = {"title_contains": "design,spec"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "att-123"

    def test_title_filter_no_match(self):
        event = AttachmentCreatedEvent(self.runtime)
        params = {"title_contains": "retro"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_source_type_filter_match(self):
        event = AttachmentCreatedEvent(self.runtime)
        params = {"source_type_filter": "slack,github"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["sourceType"] == "github"

    def test_source_type_filter_no_match(self):
        event = AttachmentCreatedEvent(self.runtime)
        params = {"source_type_filter": "slack,figma"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_issue_filter_match(self):
        event = AttachmentCreatedEvent(self.runtime)
        params = {"issue_filter": "ISSUE-1,ISSUE-9"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["issueId"] == "ISSUE-1"

    def test_issue_filter_no_match(self):
        event = AttachmentCreatedEvent(self.runtime)
        params = {"issue_filter": "ISSUE-99"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_multiple_filters_all_match(self):
        event = AttachmentCreatedEvent(self.runtime)
        params = {
            "title_contains": "Design",
            "source_type_filter": "github",
            "issue_filter": "ISSUE-1",
        }

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "att-123"

    def test_missing_payload(self):
        event = AttachmentCreatedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

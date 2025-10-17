import copy

import pytest

from events.issue_relation.issue_relation_created import IssueRelationCreatedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestIssueRelationCreatedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "create",
            "type": "IssueRelation",
            "data": {
                "id": "rel-123",
                "type": "blocks",
                "issueId": "issue-123",
                "relatedIssueId": "issue-456",
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = IssueRelationCreatedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "create"
        assert result.variables["data"]["type"] == "blocks"

    def test_relation_type_filter_match(self):
        event = IssueRelationCreatedEvent(self.runtime)
        params = {"relation_type_filter": "blocks,duplicates"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "rel-123"

    def test_relation_type_filter_no_match(self):
        event = IssueRelationCreatedEvent(self.runtime)
        params = {"relation_type_filter": "duplicates,relates"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_issue_filter_match_primary(self):
        event = IssueRelationCreatedEvent(self.runtime)
        params = {"issue_filter": "issue-123"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["issueId"] == "issue-123"

    def test_issue_filter_match_related(self):
        event = IssueRelationCreatedEvent(self.runtime)
        params = {"issue_filter": "issue-456"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["relatedIssueId"] == "issue-456"

    def test_issue_filter_no_match(self):
        event = IssueRelationCreatedEvent(self.runtime)
        params = {"issue_filter": "issue-999"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_missing_payload(self):
        event = IssueRelationCreatedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

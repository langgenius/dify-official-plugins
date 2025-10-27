import copy

import pytest

from events.issue_relation.issue_relation_updated import IssueRelationUpdatedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestIssueRelationUpdatedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "update",
            "type": "IssueRelation",
            "data": {
                "id": "rel-123",
                "type": "duplicates",
                "issueId": "issue-123",
                "relatedIssueId": "issue-789",
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = IssueRelationUpdatedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "update"
        assert result.variables["data"]["type"] == "duplicates"

    def test_relation_type_filter(self):
        event = IssueRelationUpdatedEvent(self.runtime)
        params = {"relation_type_filter": "duplicates"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "rel-123"

    def test_relation_type_filter_no_match(self):
        event = IssueRelationUpdatedEvent(self.runtime)
        params = {"relation_type_filter": "blocks"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_issue_filter_matches_related(self):
        event = IssueRelationUpdatedEvent(self.runtime)
        params = {"issue_filter": "issue-789"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["relatedIssueId"] == "issue-789"

    def test_issue_filter_no_match(self):
        event = IssueRelationUpdatedEvent(self.runtime)
        params = {"issue_filter": "issue-001"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_missing_payload(self):
        event = IssueRelationUpdatedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

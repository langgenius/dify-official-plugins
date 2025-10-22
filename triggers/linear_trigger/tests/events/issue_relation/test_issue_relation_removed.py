import copy

import pytest

from events.issue_relation.issue_relation_removed import IssueRelationRemovedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestIssueRelationRemovedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "remove",
            "type": "IssueRelation",
            "data": {
                "id": "rel-123",
                "type": "relates",
                "issueId": "issue-321",
                "relatedIssueId": "issue-654",
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = IssueRelationRemovedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "remove"
        assert result.variables["data"]["type"] == "relates"

    def test_relation_type_filter(self):
        event = IssueRelationRemovedEvent(self.runtime)
        params = {"relation_type_filter": "relates"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "rel-123"

    def test_relation_type_filter_no_match(self):
        event = IssueRelationRemovedEvent(self.runtime)
        params = {"relation_type_filter": "blocks"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_issue_filter_primary_match(self):
        event = IssueRelationRemovedEvent(self.runtime)
        params = {"issue_filter": "issue-321"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["issueId"] == "issue-321"

    def test_issue_filter_no_match(self):
        event = IssueRelationRemovedEvent(self.runtime)
        params = {"issue_filter": "issue-999"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_missing_payload(self):
        event = IssueRelationRemovedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

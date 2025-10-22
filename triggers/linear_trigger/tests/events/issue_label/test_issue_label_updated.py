import copy

import pytest

from events.issue_label.issue_label_updated import IssueLabelUpdatedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestIssueLabelUpdatedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "update",
            "type": "IssueLabel",
            "data": {
                "id": "label-123",
                "name": "Priority: Critical",
                "description": "Updated critical status",
                "color": "#FFAA00",
                "teamId": "team-1",
                "parentId": None,
                "creatorId": "user-1",
                "inheritedFromId": None,
                "isGroup": True,
                "createdAt": "2025-10-16T12:00:00.000Z",
                "updatedAt": "2025-10-16T13:00:00.000Z",
                "archivedAt": None,
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = IssueLabelUpdatedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "update"
        assert result.variables["data"]["isGroup"] is True

    def test_name_filter(self):
        event = IssueLabelUpdatedEvent(self.runtime)
        params = {"name_contains": "critical"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "label-123"

    def test_name_filter_no_match(self):
        event = IssueLabelUpdatedEvent(self.runtime)
        params = {"name_contains": "backlog"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_color_filter(self):
        event = IssueLabelUpdatedEvent(self.runtime)
        params = {"color_filter": "#ffaa00"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["color"] == "#FFAA00"

    def test_color_filter_no_match(self):
        event = IssueLabelUpdatedEvent(self.runtime)
        params = {"color_filter": "#00ff00"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_team_filter(self):
        event = IssueLabelUpdatedEvent(self.runtime)
        params = {"team_filter": "team-1"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["teamId"] == "team-1"

    def test_team_filter_no_match(self):
        event = IssueLabelUpdatedEvent(self.runtime)
        params = {"team_filter": "team-2"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_group_only_filter(self):
        event = IssueLabelUpdatedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {"group_only": "true"})

        assert result.variables["data"]["isGroup"] is True

    def test_group_only_filter_no_match(self):
        payload = copy.deepcopy(self.base_payload)
        payload["data"]["isGroup"] = False

        event = IssueLabelUpdatedEvent(self.runtime)
        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(payload), {"group_only": True})

    def test_missing_payload(self):
        event = IssueLabelUpdatedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

import copy

import pytest

from events.issue_label.issue_label_removed import IssueLabelRemovedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestIssueLabelRemovedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "remove",
            "type": "IssueLabel",
            "data": {
                "id": "label-123",
                "name": "Priority: Critical",
                "description": "Deprecated label",
                "color": "#FFAA00",
                "teamId": "team-1",
                "parentId": None,
                "creatorId": "user-1",
                "inheritedFromId": None,
                "isGroup": False,
                "createdAt": "2025-10-10T12:00:00.000Z",
                "updatedAt": "2025-10-12T12:00:00.000Z",
                "archivedAt": "2025-10-16T12:30:00.000Z",
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = IssueLabelRemovedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "remove"
        assert result.variables["data"]["archivedAt"] == "2025-10-16T12:30:00.000Z"

    def test_name_filter(self):
        event = IssueLabelRemovedEvent(self.runtime)
        params = {"name_contains": "critical"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "label-123"

    def test_name_filter_no_match(self):
        event = IssueLabelRemovedEvent(self.runtime)
        params = {"name_contains": "backlog"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_color_filter(self):
        event = IssueLabelRemovedEvent(self.runtime)
        params = {"color_filter": "#ffaa00"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["color"] == "#FFAA00"

    def test_color_filter_no_match(self):
        event = IssueLabelRemovedEvent(self.runtime)
        params = {"color_filter": "#00ff00"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_team_filter(self):
        event = IssueLabelRemovedEvent(self.runtime)
        params = {"team_filter": "team-1"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["teamId"] == "team-1"

    def test_team_filter_no_match(self):
        event = IssueLabelRemovedEvent(self.runtime)
        params = {"team_filter": "team-2"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_group_only_filter(self):
        payload = copy.deepcopy(self.base_payload)
        payload["data"]["isGroup"] = True

        event = IssueLabelRemovedEvent(self.runtime)
        result = event._on_event(self._make_request(payload), {"group_only": "true"})

        assert result.variables["data"]["isGroup"] is True

    def test_group_only_filter_no_match(self):
        event = IssueLabelRemovedEvent(self.runtime)
        params = {"group_only": True}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_missing_payload(self):
        event = IssueLabelRemovedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

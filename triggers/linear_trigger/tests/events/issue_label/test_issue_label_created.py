import copy

import pytest

from events.issue_label.issue_label_created import IssueLabelCreatedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestIssueLabelCreatedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "create",
            "type": "IssueLabel",
            "data": {
                "id": "label-123",
                "name": "Priority: Urgent",
                "description": "Issues that must be resolved immediately",
                "color": "#FF0000",
                "teamId": "team-1",
                "parentId": None,
                "creatorId": "user-1",
                "inheritedFromId": None,
                "isGroup": False,
                "createdAt": "2025-10-16T12:00:00.000Z",
                "updatedAt": "2025-10-16T12:00:00.000Z",
                "archivedAt": None,
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = IssueLabelCreatedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "create"
        assert result.variables["data"]["name"] == "Priority: Urgent"

    def test_name_filter_match(self):
        event = IssueLabelCreatedEvent(self.runtime)
        params = {"name_contains": "urgent"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "label-123"

    def test_name_filter_no_match(self):
        event = IssueLabelCreatedEvent(self.runtime)
        params = {"name_contains": "backlog"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_color_filter_match(self):
        event = IssueLabelCreatedEvent(self.runtime)
        params = {"color_filter": "#ff0000, #00ff00"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["color"] == "#FF0000"

    def test_color_filter_no_match(self):
        event = IssueLabelCreatedEvent(self.runtime)
        params = {"color_filter": "#00ff00"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_team_filter_match(self):
        event = IssueLabelCreatedEvent(self.runtime)
        params = {"team_filter": "team-1,team-2"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["teamId"] == "team-1"

    def test_team_filter_no_match(self):
        event = IssueLabelCreatedEvent(self.runtime)
        params = {"team_filter": "team-9"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_group_only_filter(self):
        payload = copy.deepcopy(self.base_payload)
        payload["data"]["isGroup"] = True

        event = IssueLabelCreatedEvent(self.runtime)
        result = event._on_event(self._make_request(payload), {"group_only": True})

        assert result.variables["data"]["isGroup"] is True

    def test_group_only_filter_excludes_non_group(self):
        event = IssueLabelCreatedEvent(self.runtime)
        params = {"group_only": "true"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_missing_payload(self):
        event = IssueLabelCreatedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

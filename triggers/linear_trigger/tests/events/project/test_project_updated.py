import copy

import pytest

from events.project.project_updated import ProjectUpdatedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestProjectUpdatedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "update",
            "type": "Project",
            "data": {
                "id": "project-123",
                "name": "Q4 Product Launch",
                "description": "Launch new features in Q4",
                "priority": 2,
                "url": "https://linear.app/company/project/q4-product-launch",
                "startDate": "2025-10-01",
                "targetDate": "2025-12-31",
                "updatedAt": "2025-10-20T12:10:00.000Z",
                "startedAt": "2025-10-20T12:00:00.000Z",
                "completedAt": None,
                "canceledAt": None,
                "statusId": "status-started",
                "status": {
                    "id": "status-started",
                    "name": "In Progress",
                    "type": "started",
                },
                "teamIds": ["team-123", "team-456"],
            },
            "actor": {
                "id": "user-123",
                "name": "Test User",
            },
            "updatedFrom": {
                "statusId": "status-planned",
                "status": {
                    "id": "status-planned",
                    "name": "Planned",
                    "type": "planned",
                },
                "startedAt": None,
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = ProjectUpdatedEvent(self.runtime)
        request = self._make_request(self.base_payload)

        result = event._on_event(request, {})
        assert result.variables["action"] == "update"
        assert result.variables["data"]["statusId"] == "status-started"

    def test_name_contains_match(self):
        event = ProjectUpdatedEvent(self.runtime)
        request = self._make_request(self.base_payload)
        parameters = {"name_contains": "product,launch"}

        result = event._on_event(request, parameters)
        assert "launch" in result.variables["data"]["name"].lower()

    def test_status_changed_filter_allows_transition(self):
        event = ProjectUpdatedEvent(self.runtime)
        request = self._make_request(self.base_payload)
        parameters = {"status_changed": True}

        result = event._on_event(request, parameters)
        assert result.variables["data"]["status"]["type"] == "started"

    def test_status_changed_filter_requires_change(self):
        payload = copy.deepcopy(self.base_payload)
        payload["updatedFrom"] = {"name": "Q4 Product Launch"}

        event = ProjectUpdatedEvent(self.runtime)
        request = self._make_request(payload)
        parameters = {"status_changed": True}

        with pytest.raises(EventIgnoreError):
            event._on_event(request, parameters)

    def test_status_changed_filter_without_previous_state(self):
        payload = copy.deepcopy(self.base_payload)
        payload.pop("updatedFrom", None)

        event = ProjectUpdatedEvent(self.runtime)
        request = self._make_request(payload)
        parameters = {"status_changed": True}

        with pytest.raises(EventIgnoreError):
            event._on_event(request, parameters)

    def test_status_changed_detects_completion_timestamps(self):
        payload = copy.deepcopy(self.base_payload)
        payload["data"]["completedAt"] = "2025-12-01T00:00:00.000Z"
        payload["updatedFrom"] = {"completedAt": None}

        event = ProjectUpdatedEvent(self.runtime)
        request = self._make_request(payload)
        parameters = {"status_changed": True}

        result = event._on_event(request, parameters)
        assert result.variables["data"]["completedAt"] == "2025-12-01T00:00:00.000Z"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

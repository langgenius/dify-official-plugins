import copy

import pytest

from events.initiative.initiative_removed import InitiativeRemovedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestInitiativeRemovedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "remove",
            "type": "Initiative",
            "data": {
                "id": "initiative-789",
                "name": "Legacy Migration",
                "description": "Migration complete, initiative retired.",
                "status": "completed",
                "health": "completed",
                "ownerId": "user-owner",
                "creatorId": "user-creator",
                "organizationId": "org-1",
                "projects": [
                    {"id": "project-777", "name": "Data Platform"},
                ],
                "startedAt": "2025-01-01",
                "targetDate": "2025-06-30",
                "completedAt": "2025-06-25",
                "healthUpdatedAt": "2025-06-25T10:00:00.000Z",
                "createdAt": "2024-12-01T09:00:00.000Z",
                "updatedAt": "2025-06-25T10:00:00.000Z",
                "url": "https://linear.app/workspace/initiative/initiative-789",
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = InitiativeRemovedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "remove"
        assert result.variables["data"]["status"] == "completed"

    def test_name_filter(self):
        event = InitiativeRemovedEvent(self.runtime)
        params = {"name_contains": "legacy"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "initiative-789"

    def test_name_filter_no_match(self):
        event = InitiativeRemovedEvent(self.runtime)
        params = {"name_contains": "revamp"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_status_filter(self):
        event = InitiativeRemovedEvent(self.runtime)
        params = {"status_filter": "completed"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["status"] == "completed"

    def test_status_filter_no_match(self):
        event = InitiativeRemovedEvent(self.runtime)
        params = {"status_filter": "in_progress"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_owner_filter(self):
        event = InitiativeRemovedEvent(self.runtime)
        params = {"owner_filter": "user-owner"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["ownerId"] == "user-owner"

    def test_owner_filter_no_match(self):
        event = InitiativeRemovedEvent(self.runtime)
        params = {"owner_filter": "user-other"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_health_filter(self):
        event = InitiativeRemovedEvent(self.runtime)
        params = {"health_filter": "completed"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["health"] == "completed"

    def test_health_filter_no_match(self):
        event = InitiativeRemovedEvent(self.runtime)
        params = {"health_filter": "at_risk"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_project_filter_match(self):
        event = InitiativeRemovedEvent(self.runtime)
        params = {"project_filter": "project-777"}

        result = event._on_event(self._make_request(self.base_payload), params)
        project_ids = {project["id"] for project in result.variables["data"]["projects"]}
        assert "project-777" in project_ids

    def test_project_filter_no_match(self):
        event = InitiativeRemovedEvent(self.runtime)
        params = {"project_filter": "project-999"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_missing_payload(self):
        event = InitiativeRemovedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

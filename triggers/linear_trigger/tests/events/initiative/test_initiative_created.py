import copy

import pytest

from events.initiative.initiative_created import InitiativeCreatedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestInitiativeCreatedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "create",
            "type": "Initiative",
            "data": {
                "id": "initiative-123",
                "name": "Mobile Onboarding Revamp",
                "description": "Improve the first run experience on iOS and Android.",
                "status": "planned",
                "health": "on_track",
                "ownerId": "user-owner",
                "creatorId": "user-creator",
                "organizationId": "org-1",
                "projects": [
                    {"id": "project-111", "name": "iOS App"},
                    {"id": "project-222", "name": "Android App"},
                ],
                "startedAt": None,
                "targetDate": "2026-01-31",
                "completedAt": None,
                "healthUpdatedAt": "2025-10-16T09:00:00.000Z",
                "createdAt": "2025-10-16T09:00:00.000Z",
                "updatedAt": "2025-10-16T09:00:00.000Z",
                "url": "https://linear.app/workspace/initiative/initiative-123",
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = InitiativeCreatedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "create"
        assert result.variables["data"]["status"] == "planned"

    def test_name_filter_match(self):
        event = InitiativeCreatedEvent(self.runtime)
        params = {"name_contains": "mobile,revamp"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "initiative-123"

    def test_name_filter_no_match(self):
        event = InitiativeCreatedEvent(self.runtime)
        params = {"name_contains": "backend"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_status_filter(self):
        event = InitiativeCreatedEvent(self.runtime)
        params = {"status_filter": "planned,in_progress"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["status"] == "planned"

    def test_status_filter_no_match(self):
        event = InitiativeCreatedEvent(self.runtime)
        params = {"status_filter": "completed"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_owner_filter(self):
        event = InitiativeCreatedEvent(self.runtime)
        params = {"owner_filter": "user-owner"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["ownerId"] == "user-owner"

    def test_owner_filter_no_match(self):
        event = InitiativeCreatedEvent(self.runtime)
        params = {"owner_filter": "user-other"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_health_filter(self):
        event = InitiativeCreatedEvent(self.runtime)
        params = {"health_filter": "on_track"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["health"] == "on_track"

    def test_health_filter_no_match(self):
        event = InitiativeCreatedEvent(self.runtime)
        params = {"health_filter": "at_risk"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_project_filter_match(self):
        event = InitiativeCreatedEvent(self.runtime)
        params = {"project_filter": "project-222"}

        result = event._on_event(self._make_request(self.base_payload), params)
        project_ids = {project["id"] for project in result.variables["data"]["projects"]}
        assert "project-222" in project_ids

    def test_project_filter_no_match(self):
        event = InitiativeCreatedEvent(self.runtime)
        params = {"project_filter": "project-999"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_missing_payload(self):
        event = InitiativeCreatedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

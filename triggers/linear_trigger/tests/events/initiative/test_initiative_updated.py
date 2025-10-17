import copy

import pytest

from events.initiative.initiative_updated import InitiativeUpdatedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestInitiativeUpdatedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "update",
            "type": "Initiative",
            "data": {
                "id": "initiative-456",
                "name": "Mobile Onboarding Revamp",
                "description": "Scope adjusted to include beta feedback.",
                "status": "in_progress",
                "health": "at_risk",
                "ownerId": "user-owner",
                "creatorId": "user-creator",
                "organizationId": "org-1",
                "projects": [
                    {"id": "project-111", "name": "iOS App"},
                    {"id": "project-333", "name": "Analytics Dashboard"},
                ],
                "startedAt": "2025-11-01",
                "targetDate": "2026-02-28",
                "completedAt": None,
                "healthUpdatedAt": "2025-11-15T09:00:00.000Z",
                "createdAt": "2025-10-16T09:00:00.000Z",
                "updatedAt": "2025-11-15T09:00:00.000Z",
                "url": "https://linear.app/workspace/initiative/initiative-456",
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = InitiativeUpdatedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "update"
        assert result.variables["data"]["status"] == "in_progress"

    def test_name_filter(self):
        event = InitiativeUpdatedEvent(self.runtime)
        params = {"name_contains": "revamp"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "initiative-456"

    def test_name_filter_no_match(self):
        event = InitiativeUpdatedEvent(self.runtime)
        params = {"name_contains": "backend"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_status_filter(self):
        event = InitiativeUpdatedEvent(self.runtime)
        params = {"status_filter": "in_progress"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["status"] == "in_progress"

    def test_status_filter_no_match(self):
        event = InitiativeUpdatedEvent(self.runtime)
        params = {"status_filter": "completed"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_owner_filter(self):
        event = InitiativeUpdatedEvent(self.runtime)
        params = {"owner_filter": "user-owner"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["ownerId"] == "user-owner"

    def test_owner_filter_no_match(self):
        event = InitiativeUpdatedEvent(self.runtime)
        params = {"owner_filter": "user-other"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_health_filter(self):
        event = InitiativeUpdatedEvent(self.runtime)
        params = {"health_filter": "at_risk"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["health"] == "at_risk"

    def test_health_filter_no_match(self):
        event = InitiativeUpdatedEvent(self.runtime)
        params = {"health_filter": "on_track"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_project_filter_match(self):
        event = InitiativeUpdatedEvent(self.runtime)
        params = {"project_filter": "project-333"}

        result = event._on_event(self._make_request(self.base_payload), params)
        project_ids = {project["id"] for project in result.variables["data"]["projects"]}
        assert "project-333" in project_ids

    def test_project_filter_no_match(self):
        event = InitiativeUpdatedEvent(self.runtime)
        params = {"project_filter": "project-999"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_missing_payload(self):
        event = InitiativeUpdatedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

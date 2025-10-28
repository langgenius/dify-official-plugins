import copy

import pytest

from events.initiative_update.initiative_update_created import InitiativeUpdateCreatedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestInitiativeUpdateCreatedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "create",
            "type": "InitiativeUpdate",
            "data": {
                "id": "init-update-1",
                "body": "Completed the onboarding flow research and defined milestones.",
                "bodyData": '{"blocks":[]}',
                "health": "on_track",
                "initiativeId": "initiative-123",
                "slugId": "week-1",
                "url": "https://linear.app/workspace/initiative/initiative-123/update/week-1",
                "userId": "user-1",
                "createdAt": "2025-10-16T10:00:00.000Z",
                "updatedAt": "2025-10-16T10:00:00.000Z",
                "editedAt": "2025-10-16T10:00:00.000Z",
                "reactionData": {"total": 2},
                "initiative": {"id": "initiative-123", "name": "Mobile Onboarding Revamp"},
                "user": {"id": "user-1", "name": "Product Manager"},
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = InitiativeUpdateCreatedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "create"
        assert result.variables["data"]["initiativeId"] == "initiative-123"

    def test_body_filter(self):
        event = InitiativeUpdateCreatedEvent(self.runtime)
        params = {"body_contains": "milestones"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "init-update-1"

    def test_body_filter_no_match(self):
        event = InitiativeUpdateCreatedEvent(self.runtime)
        params = {"body_contains": "backend"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_health_filter(self):
        event = InitiativeUpdateCreatedEvent(self.runtime)
        params = {"health_filter": "on_track"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["health"] == "on_track"

    def test_health_filter_no_match(self):
        event = InitiativeUpdateCreatedEvent(self.runtime)
        params = {"health_filter": "at_risk"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_initiative_filter(self):
        event = InitiativeUpdateCreatedEvent(self.runtime)
        params = {"initiative_filter": "initiative-123"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["initiativeId"] == "initiative-123"

    def test_initiative_filter_no_match(self):
        event = InitiativeUpdateCreatedEvent(self.runtime)
        params = {"initiative_filter": "initiative-999"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_author_filter(self):
        event = InitiativeUpdateCreatedEvent(self.runtime)
        params = {"author_filter": "user-1"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["userId"] == "user-1"

    def test_author_filter_no_match(self):
        event = InitiativeUpdateCreatedEvent(self.runtime)
        params = {"author_filter": "user-9"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_missing_payload(self):
        event = InitiativeUpdateCreatedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

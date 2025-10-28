import copy

import pytest

from events.initiative_update.initiative_update_updated import InitiativeUpdateUpdatedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestInitiativeUpdateUpdatedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "update",
            "type": "InitiativeUpdate",
            "data": {
                "id": "init-update-2",
                "body": "Timeline adjusted to accommodate beta learnings.",
                "bodyData": '{"blocks":[]}',
                "health": "at_risk",
                "initiativeId": "initiative-123",
                "slugId": "week-2",
                "url": "https://linear.app/workspace/initiative/initiative-123/update/week-2",
                "userId": "user-2",
                "createdAt": "2025-10-23T10:00:00.000Z",
                "updatedAt": "2025-10-23T10:00:00.000Z",
                "editedAt": "2025-10-23T10:00:00.000Z",
                "reactionData": {"total": 5},
                "initiative": {"id": "initiative-123", "name": "Mobile Onboarding Revamp"},
                "user": {"id": "user-2", "name": "Engineering Manager"},
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = InitiativeUpdateUpdatedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "update"
        assert result.variables["data"]["health"] == "at_risk"

    def test_body_filter(self):
        event = InitiativeUpdateUpdatedEvent(self.runtime)
        params = {"body_contains": "beta"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["initiativeId"] == "initiative-123"

    def test_body_filter_no_match(self):
        event = InitiativeUpdateUpdatedEvent(self.runtime)
        params = {"body_contains": "release"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_health_filter(self):
        event = InitiativeUpdateUpdatedEvent(self.runtime)
        params = {"health_filter": "at_risk"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["health"] == "at_risk"

    def test_health_filter_no_match(self):
        event = InitiativeUpdateUpdatedEvent(self.runtime)
        params = {"health_filter": "on_track"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_initiative_filter(self):
        event = InitiativeUpdateUpdatedEvent(self.runtime)
        params = {"initiative_filter": "initiative-123"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["initiativeId"] == "initiative-123"

    def test_initiative_filter_no_match(self):
        event = InitiativeUpdateUpdatedEvent(self.runtime)
        params = {"initiative_filter": "initiative-999"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_author_filter(self):
        event = InitiativeUpdateUpdatedEvent(self.runtime)
        params = {"author_filter": "user-2"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["userId"] == "user-2"

    def test_author_filter_no_match(self):
        event = InitiativeUpdateUpdatedEvent(self.runtime)
        params = {"author_filter": "user-1"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_missing_payload(self):
        event = InitiativeUpdateUpdatedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

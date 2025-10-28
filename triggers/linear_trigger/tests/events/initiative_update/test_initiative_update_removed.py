import copy

import pytest

from events.initiative_update.initiative_update_removed import InitiativeUpdateRemovedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestInitiativeUpdateRemovedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "remove",
            "type": "InitiativeUpdate",
            "data": {
                "id": "init-update-3",
                "body": "Final update removed because the initiative has closed.",
                "bodyData": '{"blocks":[]}',
                "health": "completed",
                "initiativeId": "initiative-789",
                "slugId": "final-update",
                "url": "https://linear.app/workspace/initiative/initiative-789/update/final-update",
                "userId": "user-4",
                "createdAt": "2025-07-10T10:00:00.000Z",
                "updatedAt": "2025-07-20T10:00:00.000Z",
                "editedAt": "2025-07-20T10:00:00.000Z",
                "reactionData": {"total": 0},
                "initiative": {"id": "initiative-789", "name": "Legacy Migration"},
                "user": {"id": "user-4", "name": "Operations"},
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = InitiativeUpdateRemovedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "remove"
        assert result.variables["data"]["initiativeId"] == "initiative-789"

    def test_body_filter(self):
        event = InitiativeUpdateRemovedEvent(self.runtime)
        params = {"body_contains": "final,closed"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "init-update-3"

    def test_body_filter_no_match(self):
        event = InitiativeUpdateRemovedEvent(self.runtime)
        params = {"body_contains": "progress"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_health_filter(self):
        event = InitiativeUpdateRemovedEvent(self.runtime)
        params = {"health_filter": "completed"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["health"] == "completed"

    def test_health_filter_no_match(self):
        event = InitiativeUpdateRemovedEvent(self.runtime)
        params = {"health_filter": "at_risk"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_initiative_filter(self):
        event = InitiativeUpdateRemovedEvent(self.runtime)
        params = {"initiative_filter": "initiative-789"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["initiativeId"] == "initiative-789"

    def test_initiative_filter_no_match(self):
        event = InitiativeUpdateRemovedEvent(self.runtime)
        params = {"initiative_filter": "initiative-000"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_author_filter(self):
        event = InitiativeUpdateRemovedEvent(self.runtime)
        params = {"author_filter": "user-4"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["userId"] == "user-4"

    def test_author_filter_no_match(self):
        event = InitiativeUpdateRemovedEvent(self.runtime)
        params = {"author_filter": "user-1"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_missing_payload(self):
        event = InitiativeUpdateRemovedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

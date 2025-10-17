import copy

import pytest

from events.project_update.project_update_removed import ProjectUpdateRemovedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestProjectUpdateRemovedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "remove",
            "type": "ProjectUpdate",
            "data": {
                "id": "proj-update-3",
                "body": "Deprecated weekly update will be replaced.",
                "bodyData": '{"blocks":[]}',
                "health": "off_track",
                "projectId": "project-999",
                "slugId": "legacy-update",
                "url": "https://linear.app/workspace/project/project-999/update/legacy-update",
                "userId": "user-3",
                "createdAt": "2025-10-01T08:00:00.000Z",
                "updatedAt": "2025-10-10T08:00:00.000Z",
                "editedAt": "2025-10-10T08:00:00.000Z",
                "reactionData": {"total": 1},
                "project": {"id": "project-999", "name": "Legacy Maintenance"},
                "user": {"id": "user-3", "name": "Operations"},
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = ProjectUpdateRemovedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "remove"
        assert result.variables["data"]["id"] == "proj-update-3"

    def test_body_filter(self):
        event = ProjectUpdateRemovedEvent(self.runtime)
        params = {"body_contains": "deprecated"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["body"].startswith("Deprecated")

    def test_body_filter_no_match(self):
        event = ProjectUpdateRemovedEvent(self.runtime)
        params = {"body_contains": "analytics"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_health_filter(self):
        event = ProjectUpdateRemovedEvent(self.runtime)
        params = {"health_filter": "off_track"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["health"] == "off_track"

    def test_health_filter_no_match(self):
        event = ProjectUpdateRemovedEvent(self.runtime)
        params = {"health_filter": "on_track"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_project_filter(self):
        event = ProjectUpdateRemovedEvent(self.runtime)
        params = {"project_filter": "project-999"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["projectId"] == "project-999"

    def test_project_filter_no_match(self):
        event = ProjectUpdateRemovedEvent(self.runtime)
        params = {"project_filter": "project-123"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_author_filter(self):
        event = ProjectUpdateRemovedEvent(self.runtime)
        params = {"author_filter": "user-3"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["userId"] == "user-3"

    def test_author_filter_no_match(self):
        event = ProjectUpdateRemovedEvent(self.runtime)
        params = {"author_filter": "user-1"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_missing_payload(self):
        event = ProjectUpdateRemovedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

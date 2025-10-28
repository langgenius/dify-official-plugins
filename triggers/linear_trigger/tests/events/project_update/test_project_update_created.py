import copy

import pytest

from events.project_update.project_update_created import ProjectUpdateCreatedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestProjectUpdateCreatedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "create",
            "type": "ProjectUpdate",
            "data": {
                "id": "proj-update-1",
                "body": "Shipped the authentication module and wrapped QA.",
                "bodyData": '{"blocks":[]}',
                "health": "on_track",
                "projectId": "project-123",
                "slugId": "week-42-update",
                "url": "https://linear.app/workspace/project/project-123/update/week-42-update",
                "userId": "user-1",
                "createdAt": "2025-10-16T08:00:00.000Z",
                "updatedAt": "2025-10-16T08:00:00.000Z",
                "editedAt": "2025-10-16T08:00:00.000Z",
                "reactionData": {"total": 3},
                "project": {"id": "project-123", "name": "Launch App"},
                "user": {"id": "user-1", "name": "Product Manager"},
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = ProjectUpdateCreatedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "create"
        assert result.variables["data"]["projectId"] == "project-123"

    def test_body_filter_match(self):
        event = ProjectUpdateCreatedEvent(self.runtime)
        params = {"body_contains": "authentication,QA"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "proj-update-1"

    def test_body_filter_no_match(self):
        event = ProjectUpdateCreatedEvent(self.runtime)
        params = {"body_contains": "infra"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_health_filter(self):
        event = ProjectUpdateCreatedEvent(self.runtime)
        params = {"health_filter": "at_risk,on_track"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["health"] == "on_track"

    def test_health_filter_no_match(self):
        event = ProjectUpdateCreatedEvent(self.runtime)
        params = {"health_filter": "at_risk"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_project_filter(self):
        event = ProjectUpdateCreatedEvent(self.runtime)
        params = {"project_filter": "project-123"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["projectId"] == "project-123"

    def test_project_filter_no_match(self):
        event = ProjectUpdateCreatedEvent(self.runtime)
        params = {"project_filter": "project-999"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_author_filter_match(self):
        event = ProjectUpdateCreatedEvent(self.runtime)
        params = {"author_filter": "user-1,user-2"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["userId"] == "user-1"

    def test_author_filter_no_match(self):
        event = ProjectUpdateCreatedEvent(self.runtime)
        params = {"author_filter": "user-9"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_missing_payload(self):
        event = ProjectUpdateCreatedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})

    def test_missing_data_section(self):
        event = ProjectUpdateCreatedEvent(self.runtime)
        with pytest.raises(ValueError, match="No project update data in payload"):
            event._on_event(self._make_request({"action": "create", "type": "ProjectUpdate"}), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

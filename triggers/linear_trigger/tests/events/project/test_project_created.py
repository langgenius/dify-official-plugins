import pytest

from events.project.project_created import ProjectCreatedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestProjectCreatedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "create",
            "type": "Project",
            "data": {
                "id": "project-123",
                "name": "Q4 Product Launch",
                "description": "Launch new features in Q4",
                "color": "#3b82f6",
                "priority": 2,
                "slugId": "q4-product-launch",
                "url": "https://linear.app/company/project/q4-product-launch",
                "startDate": "2025-10-01",
                "targetDate": "2025-12-31",
                "createdAt": "2025-10-16T12:00:00.000Z",
                "updatedAt": "2025-10-16T12:00:00.000Z",
                "lead": {
                    "id": "user-123",
                    "name": "Test Lead",
                    "email": "lead@example.com"
                },
                "leadId": "user-123",
                "status": {
                    "id": "status-123",
                    "name": "Planned",
                    "type": "planned"
                },
                "statusId": "status-123",
                "teamIds": ["team-123", "team-456"],
                "memberIds": ["user-123", "user-456"]
            },
            "actor": {
                "id": "user-123",
                "name": "Test User"
            }
        }

    def test_basic_event_handling(self):
        event = ProjectCreatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        result = event._on_event(request, {})

        assert result.variables["action"] == "create"
        assert result.variables["type"] == "Project"
        assert result.variables["data"]["id"] == "project-123"
        assert result.variables["data"]["name"] == "Q4 Product Launch"

    def test_name_contains_match(self):
        event = ProjectCreatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {"name_contains": "Q4,launch,product"}

        result = event._on_event(request, parameters)
        assert "q4" in result.variables["data"]["name"].lower()

    def test_name_contains_no_match(self):
        event = ProjectCreatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {"name_contains": "Q1,Q2,Q3"}

        with pytest.raises(EventIgnoreError):
            event._on_event(request, parameters)

    def test_priority_filter_match(self):
        event = ProjectCreatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {"priority_filter": "1,2,3"}

        result = event._on_event(request, parameters)
        assert result.variables["data"]["priority"] == 2

    def test_priority_filter_no_match(self):
        event = ProjectCreatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {"priority_filter": "0,4"}

        with pytest.raises(EventIgnoreError):
            event._on_event(request, parameters)

    def test_team_filter_match(self):
        event = ProjectCreatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {"team_filter": "team-123,team-789"}

        result = event._on_event(request, parameters)
        assert "team-123" in result.variables["data"]["teamIds"]

    def test_team_filter_no_match(self):
        event = ProjectCreatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {"team_filter": "team-999,team-888"}

        with pytest.raises(EventIgnoreError):
            event._on_event(request, parameters)

    def test_multiple_filters_all_match(self):
        event = ProjectCreatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {
            "name_contains": "Q4",
            "priority_filter": "2",
            "team_filter": "team-123"
        }

        result = event._on_event(request, parameters)
        assert result.variables["data"]["id"] == "project-123"

    def test_empty_filters(self):
        event = ProjectCreatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {
            "name_contains": "",
            "priority_filter": "",
            "team_filter": ""
        }

        result = event._on_event(request, parameters)
        assert result.variables["data"]["id"] == "project-123"

    def test_missing_payload(self):
        event = ProjectCreatedEvent(self.runtime)
        request = MockRequest(None)

        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(request, {})

    def test_missing_data_field(self):
        event = ProjectCreatedEvent(self.runtime)
        request = MockRequest({"action": "create", "type": "Project"})

        with pytest.raises(ValueError, match="No project data in payload"):
            event._on_event(request, {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

import copy

import pytest

from events.user.user_updated import UserUpdatedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestUserUpdatedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "update",
            "type": "User",
            "data": {
                "id": "user-456",
                "email": "bob@example.com",
                "name": "Bob Example",
                "displayName": "Bob Example",
                "active": False,
                "admin": False,
                "guest": True,
                "app": False,
                "createdAt": "2024-10-16T12:00:00.000Z",
                "updatedAt": "2025-10-16T12:00:00.000Z",
                "url": "https://linear.app/workspace/user/user-456",
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = UserUpdatedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "update"
        assert result.variables["data"]["guest"] is True

    def test_email_filter(self):
        event = UserUpdatedEvent(self.runtime)
        params = {"email_contains": "bob"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "user-456"

    def test_active_only_blocks_inactive(self):
        event = UserUpdatedEvent(self.runtime)
        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), {"active_only": True})

    def test_guest_only(self):
        event = UserUpdatedEvent(self.runtime)
        params = {"guest_only": True}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["guest"] is True

    def test_admin_only_no_match(self):
        event = UserUpdatedEvent(self.runtime)
        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), {"admin_only": True})

    def test_exclude_app_users(self):
        payload = copy.deepcopy(self.base_payload)
        payload["data"]["app"] = True

        event = UserUpdatedEvent(self.runtime)
        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(payload), {"exclude_app_users": True})

    def test_filters_combined(self):
        event = UserUpdatedEvent(self.runtime)
        params = {
            "email_contains": "bob",
            "guest_only": True,
            "exclude_app_users": True,
        }

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "user-456"

    def test_missing_payload(self):
        event = UserUpdatedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

import copy

import pytest

from events.user.user_created import UserCreatedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestUserCreatedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "create",
            "type": "User",
            "data": {
                "id": "user-123",
                "email": "alice@example.com",
                "name": "Alice Example",
                "displayName": "Alice Example",
                "active": True,
                "admin": True,
                "guest": False,
                "app": False,
                "createdAt": "2025-10-16T12:00:00.000Z",
                "updatedAt": "2025-10-16T12:00:00.000Z",
                "url": "https://linear.app/workspace/user/user-123",
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = UserCreatedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "create"
        assert result.variables["data"]["email"] == "alice@example.com"

    def test_email_filter(self):
        event = UserCreatedEvent(self.runtime)
        params = {"email_contains": "alice"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "user-123"

    def test_email_filter_no_match(self):
        event = UserCreatedEvent(self.runtime)
        params = {"email_contains": "bob"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_active_only(self):
        event = UserCreatedEvent(self.runtime)
        params = {"active_only": True}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["active"] is True

    def test_active_only_excludes_inactive(self):
        payload = copy.deepcopy(self.base_payload)
        payload["data"]["active"] = False

        event = UserCreatedEvent(self.runtime)
        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(payload), {"active_only": True})

    def test_admin_only(self):
        event = UserCreatedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {"admin_only": True})

        assert result.variables["data"]["admin"] is True

    def test_guest_only(self):
        payload = copy.deepcopy(self.base_payload)
        payload["data"]["guest"] = True

        event = UserCreatedEvent(self.runtime)
        result = event._on_event(self._make_request(payload), {"guest_only": True})
        assert result.variables["data"]["guest"] is True

    def test_guest_only_excludes_non_guest(self):
        event = UserCreatedEvent(self.runtime)
        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), {"guest_only": True})

    def test_exclude_app_users(self):
        payload = copy.deepcopy(self.base_payload)
        payload["data"]["app"] = True

        event = UserCreatedEvent(self.runtime)
        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(payload), {"exclude_app_users": True})

    def test_missing_payload(self):
        event = UserCreatedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

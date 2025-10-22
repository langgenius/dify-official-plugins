import copy

import pytest

from events.reaction.reaction_created import ReactionCreatedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestReactionCreatedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "create",
            "type": "Reaction",
            "data": {
                "id": "reaction-123",
                "emoji": "👍",
                "issueId": "issue-123",
                "commentId": None,
                "projectUpdateId": None,
                "initiativeUpdateId": None,
                "postId": None,
                "userId": "user-1",
                "createdAt": "2025-10-16T12:00:00.000Z",
                "updatedAt": "2025-10-16T12:00:00.000Z",
                "user": {
                    "id": "user-1",
                    "name": "Test User",
                    "email": "user@example.com",
                },
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = ReactionCreatedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "create"
        assert result.variables["data"]["emoji"] == "👍"

    def test_emoji_filter_match(self):
        event = ReactionCreatedEvent(self.runtime)
        params = {"emoji_filter": "👍,🚀"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "reaction-123"

    def test_emoji_filter_no_match(self):
        event = ReactionCreatedEvent(self.runtime)
        params = {"emoji_filter": "🎉"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_target_type_filter_issue(self):
        event = ReactionCreatedEvent(self.runtime)
        params = {"target_type_filter": "issue"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["issueId"] == "issue-123"

    def test_target_type_filter_no_match(self):
        event = ReactionCreatedEvent(self.runtime)
        params = {"target_type_filter": "comment,project_update"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_user_filter_match(self):
        event = ReactionCreatedEvent(self.runtime)
        params = {"user_filter": "user-1,user-2"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["userId"] == "user-1"

    def test_user_filter_no_match(self):
        event = ReactionCreatedEvent(self.runtime)
        params = {"user_filter": "user-2"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_multiple_filters_all_match(self):
        event = ReactionCreatedEvent(self.runtime)
        params = {
            "emoji_filter": "👍",
            "target_type_filter": "issue",
            "user_filter": "user-1",
        }

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["id"] == "reaction-123"

    def test_missing_payload(self):
        event = ReactionCreatedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

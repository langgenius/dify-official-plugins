import copy

import pytest

from events.reaction.reaction_updated import ReactionUpdatedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestReactionUpdatedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "update",
            "type": "Reaction",
            "data": {
                "id": "reaction-999",
                "emoji": "🎉",
                "issueId": None,
                "commentId": "comment-456",
                "projectUpdateId": None,
                "initiativeUpdateId": None,
                "postId": None,
                "userId": "user-2",
                "createdAt": "2025-10-16T12:00:00.000Z",
                "updatedAt": "2025-10-16T13:00:00.000Z",
                "user": {
                    "id": "user-2",
                    "name": "Reviewer",
                    "email": "reviewer@example.com",
                },
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = ReactionUpdatedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "update"
        assert result.variables["data"]["commentId"] == "comment-456"

    def test_emoji_filter_match(self):
        event = ReactionUpdatedEvent(self.runtime)
        params = {"emoji_filter": "🎉"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["emoji"] == "🎉"

    def test_emoji_filter_no_match(self):
        event = ReactionUpdatedEvent(self.runtime)
        params = {"emoji_filter": "👍"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_target_type_filter(self):
        event = ReactionUpdatedEvent(self.runtime)
        params = {"target_type_filter": "comment"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["commentId"] == "comment-456"

    def test_target_type_filter_no_match(self):
        event = ReactionUpdatedEvent(self.runtime)
        params = {"target_type_filter": "issue"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_user_filter(self):
        event = ReactionUpdatedEvent(self.runtime)
        params = {"user_filter": "user-2"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["userId"] == "user-2"

    def test_user_filter_no_match(self):
        event = ReactionUpdatedEvent(self.runtime)
        params = {"user_filter": "user-1"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_missing_payload(self):
        event = ReactionUpdatedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

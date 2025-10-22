import copy

import pytest

from events.reaction.reaction_removed import ReactionRemovedEvent
from dify_plugin.errors.trigger import EventIgnoreError


class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    def get_json(self):
        return self._json_data


class MockRuntime:
    pass


class TestReactionRemovedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            "action": "remove",
            "type": "Reaction",
            "data": {
                "id": "reaction-200",
                "emoji": "🚀",
                "issueId": None,
                "commentId": None,
                "projectUpdateId": "project-update-1",
                "initiativeUpdateId": None,
                "postId": None,
                "userId": "user-3",
                "createdAt": "2025-10-15T07:00:00.000Z",
                "updatedAt": "2025-10-16T08:00:00.000Z",
                "user": {
                    "id": "user-3",
                    "name": "Status Reporter",
                    "email": "status@example.com",
                },
            },
        }

    def _make_request(self, payload):
        return MockRequest(copy.deepcopy(payload))

    def test_basic_event_handling(self):
        event = ReactionRemovedEvent(self.runtime)
        result = event._on_event(self._make_request(self.base_payload), {})

        assert result.variables["action"] == "remove"
        assert result.variables["data"]["projectUpdateId"] == "project-update-1"

    def test_emoji_filter_match(self):
        event = ReactionRemovedEvent(self.runtime)
        params = {"emoji_filter": "🚀,🎉"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["emoji"] == "🚀"

    def test_emoji_filter_no_match(self):
        event = ReactionRemovedEvent(self.runtime)
        params = {"emoji_filter": "👍"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_target_type_filter_project_update(self):
        event = ReactionRemovedEvent(self.runtime)
        params = {"target_type_filter": "project_update"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["projectUpdateId"] == "project-update-1"

    def test_target_type_filter_no_match(self):
        event = ReactionRemovedEvent(self.runtime)
        params = {"target_type_filter": "issue,comment"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_user_filter_match(self):
        event = ReactionRemovedEvent(self.runtime)
        params = {"user_filter": "user-3"}

        result = event._on_event(self._make_request(self.base_payload), params)
        assert result.variables["data"]["userId"] == "user-3"

    def test_user_filter_no_match(self):
        event = ReactionRemovedEvent(self.runtime)
        params = {"user_filter": "user-2"}

        with pytest.raises(EventIgnoreError):
            event._on_event(self._make_request(self.base_payload), params)

    def test_missing_payload(self):
        event = ReactionRemovedEvent(self.runtime)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(self._make_request(None), {})


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

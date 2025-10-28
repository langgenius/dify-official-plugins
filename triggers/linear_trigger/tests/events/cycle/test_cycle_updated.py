import pytest
from events.cycle.cycle_updated import CycleUpdatedEvent
from dify_plugin.errors.trigger import EventIgnoreError

class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data
    def get_json(self):
        return self._json_data

class MockRuntime:
    pass

class TestCycleUpdatedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            'action': 'update',
            'type': 'Cycle',
            'data': {
                'id': 'test-123',
                'title': 'Test Title',
                'name': 'Test Name',
                'body': 'Test Body',
                'email': 'test@example.com',
                'emoji': '👍'
            }
        }

    def test_basic_event_handling(self):
        event = CycleUpdatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        result = event._on_event(request, {}, request.get_json())
        assert result.variables['action'] == 'update'
        assert result.variables['type'] == 'Cycle'

    def test_filter_match(self):
        event = CycleUpdatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {'name_contains': 'test'}
        result = event._on_event(request, parameters, request.get_json())
        assert result.variables['data']['id'] == 'test-123'

    def test_filter_no_match(self):
        event = CycleUpdatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {'name_contains': 'nomatch,fail'}
        with pytest.raises(EventIgnoreError):
            event._on_event(request, parameters, request.get_json())

    def test_empty_filter(self):
        event = CycleUpdatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {'name_contains': ''}
        result = event._on_event(request, parameters, request.get_json())
        assert result.variables['data']['id'] == 'test-123'

    def test_missing_payload(self):
        event = CycleUpdatedEvent(self.runtime)
        request = MockRequest(None)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(request, {}, request.get_json())

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

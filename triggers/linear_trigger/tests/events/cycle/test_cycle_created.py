import pytest
from events.cycle.cycle_created import CycleCreatedEvent
from dify_plugin.errors.trigger import EventIgnoreError

class MockRequest:
    def __init__(self, json_data):
        self._json_data = json_data
    def get_json(self):
        return self._json_data

class MockRuntime:
    pass

class TestCycleCreatedEvent:
    def setup_method(self):
        self.runtime = MockRuntime()
        self.base_payload = {
            'action': 'create',
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
        event = CycleCreatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        result = event._on_event(request, {})
        assert result.variables['action'] == 'create'
        assert result.variables['type'] == 'Cycle'

    def test_filter_match(self):
        event = CycleCreatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {'name_contains': 'test'}
        result = event._on_event(request, parameters)
        assert result.variables['data']['id'] == 'test-123'

    def test_filter_no_match(self):
        event = CycleCreatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {'name_contains': 'nomatch,fail'}
        with pytest.raises(EventIgnoreError):
            event._on_event(request, parameters)

    def test_empty_filter(self):
        event = CycleCreatedEvent(self.runtime)
        request = MockRequest(self.base_payload)
        parameters = {'name_contains': ''}
        result = event._on_event(request, parameters)
        assert result.variables['data']['id'] == 'test-123'

    def test_missing_payload(self):
        event = CycleCreatedEvent(self.runtime)
        request = MockRequest(None)
        with pytest.raises(ValueError, match="No payload received"):
            event._on_event(request, {})

if __name__ == "__main__":
    pytest.main([__file__, "-v"])

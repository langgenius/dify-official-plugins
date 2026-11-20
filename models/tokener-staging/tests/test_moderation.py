import pytest
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import InvokeServerUnavailableError
from protocol_http import CREDENTIALS
from protocol_http import registry as registry
from protocol_http import wire as wire


@pytest.mark.parametrize("length", [0, 1, 2000, 2001, 64000, 64001])
def test_moderation_preserves_source_chunk_and_batch_boundaries(registry, wire, length):
    _, requests, replies = wire
    text = "x" * length
    chunks = [text[start : start + 2000] for start in range(0, length, 2000)]
    batches = [chunks[start : start + 32] for start in range(0, len(chunks), 32)]
    replies.extend((200, {}, {"results": [{"flagged": False} for _ in batch]}) for batch in batches)
    model = registry.get_model_instance("tokener", ModelType.MODERATION)
    assert model.invoke("omni-moderation-latest", CREDENTIALS, text) is False
    assert [request[0] for request in requests] == ["/v1/moderations"] * len(batches)
    assert [request[2] for request in requests] == [
        {"model": "omni-moderation-latest", "input": batch} for batch in batches
    ]


def test_moderation_stops_after_flagged_batch_and_propagates_failure(registry, wire):
    _, requests, replies = wire
    model = registry.get_model_instance("tokener", ModelType.MODERATION)
    replies.append((200, {}, {"results": [{"flagged": False}, {"flagged": True}]}))
    assert model.invoke("omni-moderation-latest", CREDENTIALS, "x" * 64001) is True
    assert len(requests) == 1
    replies.append((503, {}, {"error": "unavailable"}))
    with pytest.raises(InvokeServerUnavailableError):
        model.invoke("omni-moderation-latest", CREDENTIALS, "x")

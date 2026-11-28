"""Bedrock stream handler tolerates metadata arriving before messageStart.

AWS documents messageStart before metadata, but the order is not guaranteed.
Pre-fix, return_model was initialised to None and assigned only on messageStart,
so a metadata event arriving first caused LLMResultChunk validation to fail with
"Input should be a valid string [type=string_type, input_value=None]".

The fix initialises return_model = model so the usage chunk always carries the
correct model ID regardless of event order.

Regression test for https://github.com/langgenius/dify-official-plugins/issues/4347
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace

import pytest
from dify_plugin.entities.model.llm import LLMUsage

llm_mod = importlib.import_module("models.llm.llm")
BedrockLLM = llm_mod.BedrockLargeLanguageModel

MODEL = "global.anthropic.claude-sonnet-5-5"

_START = {"messageStart": {"role": "assistant"}}
_META = {
    "metadata": {
        "usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
        "metrics": {"latencyMs": 1},
    }
}


def _make_handler():
    """Return a bound-style stub that delegates to the real handler."""
    usage = LLMUsage.empty_usage().model_copy(
        update={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
    )
    stub = SimpleNamespace(_calc_response_usage=lambda *args: usage)
    return stub


@pytest.mark.parametrize(
    "events, label",
    [
        ([_START, _META], "messageStart before metadata"),
        ([_META, _START], "metadata before messageStart"),
    ],
)
def test_stream_model_id_present_regardless_of_event_order(events, label):
    """Every yielded chunk must carry a non-None model string."""
    stub = _make_handler()
    chunks = list(
        BedrockLLM._handle_converse_stream_response(
            stub, MODEL, {}, {"stream": events}, []
        )
    )
    assert chunks, f"No chunks yielded for case: {label}"
    for chunk in chunks:
        assert chunk.model == MODEL, (
            f"chunk.model is {chunk.model!r} for case: {label}"
        )

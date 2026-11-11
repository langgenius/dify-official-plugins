"""Unit tests for the stream_function_calling credential wiring.

The ``stream_function_calling`` credential was carried over from the legacy
built-in runtime but its feature declaration was never ported to
``get_customizable_model_schema``. As a result the ``STREAM_TOOL_CALL`` feature
was never declared and Agent nodes always invoked the model non-streaming,
ignoring the setting. These tests pin that the feature is now declared when the
credential is ``supported`` and absent otherwise.
"""

import pytest

from dify_plugin.entities.model import ModelFeature

from models.llm.llm import OpenAILargeLanguageModel


def _features(stream_function_calling):
    llm = OpenAILargeLanguageModel(model_schemas=[])
    entity = llm.get_customizable_model_schema(
        "gpt-5.6-luna",
        {
            "mode": "chat",
            "context_size": "922000",
            "stream_function_calling": stream_function_calling,
        },
    )
    return entity.features


def test_stream_function_calling_supported_declares_stream_tool_call():
    assert ModelFeature.STREAM_TOOL_CALL in _features("supported")


@pytest.mark.parametrize("value", ["not_supported", None])
def test_stream_function_calling_not_supported_omits_stream_tool_call(value):
    assert ModelFeature.STREAM_TOOL_CALL not in _features(value)

"""Regression test: streaming handler must preserve redacted_thinking.data.

Anthropic requires redacted_thinking blocks to be echoed back unmodified on
the tool-result turn. The streaming handler used to reconstruct the block as
{"type": "redacted_thinking"}, dropping the opaque `data` payload — producing
a malformed block that the Messages API rejects on the follow-up request.
"""

from decimal import Decimal

import pytest
from anthropic.types import (
    InputJSONDelta,
    Message,
    MessageDeltaEvent,
    MessageStartEvent,
    MessageStopEvent,
    ContentBlockDeltaEvent,
    ContentBlockStartEvent,
    RedactedThinkingBlock,
    ToolUseBlock,
    Usage,
)
from anthropic.types.message_delta_usage import MessageDeltaUsage
from anthropic.types.raw_message_delta_event import Delta
from dify_plugin.entities.model.llm import LLMUsage
from dify_plugin.entities.model.message import UserPromptMessage

from models.llm.llm import AnthropicLargeLanguageModel, LargeLanguageModel


def _usage(self, *args, **kwargs):
    return LLMUsage(
        prompt_tokens=1, prompt_unit_price=Decimal(0), prompt_price_unit=Decimal(0),
        prompt_price=Decimal(0), completion_tokens=1,
        completion_unit_price=Decimal(0), completion_price_unit=Decimal(0),
        completion_price=Decimal(0), total_tokens=2, total_price=Decimal(0),
        currency="USD", latency=0.1,
    )


@pytest.fixture(autouse=True)
def _stub_usage(monkeypatch):
    # the streaming handler computes billing at the final chunk; not under test
    monkeypatch.setattr(LargeLanguageModel, "_calc_response_usage", _usage)


def _stream_events():
    yield MessageStartEvent(
        type="message_start",
        message=Message(
            id="msg_1", type="message", role="assistant", content=[],
            model="claude-test", stop_reason=None, stop_sequence=None,
            usage=Usage(input_tokens=10, output_tokens=0),
        ),
    )
    # redacted thinking block carries an opaque encrypted payload
    yield ContentBlockStartEvent(
        type="content_block_start", index=0,
        content_block=RedactedThinkingBlock(
            type="redacted_thinking", data="ENCRYPTED_PAYLOAD_123"
        ),
    )
    # a tool_use block in the same assistant turn
    yield ContentBlockStartEvent(
        type="content_block_start", index=1,
        content_block=ToolUseBlock(
            type="tool_use", id="toolu_1", name="get_weather", input={}
        ),
    )
    yield ContentBlockDeltaEvent(
        type="content_block_delta", index=1,
        delta=InputJSONDelta(type="input_json_delta", partial_json='{"city":"Lisbon"}'),
    )
    yield MessageDeltaEvent(
        type="message_delta",
        delta=Delta(stop_reason="tool_use"),
        usage=MessageDeltaUsage(output_tokens=7),
    )
    yield MessageStopEvent(type="message_stop")


def test_streaming_preserves_redacted_thinking_data():
    model = AnthropicLargeLanguageModel()
    chunks = list(
        model._handle_chat_generate_stream_response(
            model="claude-test",
            credentials={"anthropic_api_key": "sk-test"},
            response=_stream_events(),
            prompt_messages=[UserPromptMessage(content="hi")],
        )
    )
    assert chunks, "handler produced no chunks"

    # the preserved block must round-trip the opaque data unchanged
    assert model.previous_redacted_thinking_blocks == [
        {"type": "redacted_thinking", "data": "ENCRYPTED_PAYLOAD_123"}
    ]

    # and the tool call was reconstructed alongside it
    final = chunks[-1].delta.message
    assert final.tool_calls and final.tool_calls[0].function.name == "get_weather"

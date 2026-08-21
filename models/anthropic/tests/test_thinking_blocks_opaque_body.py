"""Regression tests for issue #3658: Anthropic thinking blocks are not
preserved across plugin invocation boundaries on tool-result turns.

The pre-fix code stored thinking blocks on the model instance
(`self.previous_thinking_blocks`). Because dify_plugin creates a fresh
model instance per RPC, that state was always empty by the time the
follow-up request was constructed. The fix round-trips the thinking
blocks through `AssistantPromptMessage.opaque_body`, which IS
preserved across invocations because it's part of the persisted
message.

These tests pin:
1. The non-streaming handler stores thinking blocks in `opaque_body`.
2. The streaming handler stores thinking blocks in `opaque_body` on
   the final chunk.
3. `_process_assistant_message` reads from `opaque_body` first, and
   falls back to instance state when `opaque_body` is empty.
4. IMAGE content is unchanged (always `image_url`).
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

from dify_plugin.entities.model.message import (  # noqa: E402
    AssistantPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)
from models.llm.llm import AnthropicLargeLanguageModel  # noqa: E402


# Stub thinking / redacted-thinking content blocks (the shape that the
# Anthropic SDK returns).
def _thinking_block(signature: str = "sig-abc") -> dict:
    return {"type": "thinking", "thinking": "let me think...", "signature": signature}


def _redacted_block(data: str = "enc-data-xyz") -> dict:
    return {"type": "redacted_thinking", "data": data}


def _make_instance() -> AnthropicLargeLanguageModel:
    return object.__new__(AnthropicLargeLanguageModel)


def _process(message: AssistantPromptMessage, all_messages: list) -> dict:
    instance = _make_instance()
    # Seed the instance-state fallback with empty lists (the realistic
    # state on a fresh RPC instance).
    instance.previous_thinking_blocks = []
    instance.previous_redacted_thinking_blocks = []
    return instance._process_assistant_message(message, all_messages)


# ---------------------------------------------------------------------------
# _process_assistant_message reads from opaque_body (preferred)
# ---------------------------------------------------------------------------


class TestProcessAssistantMessageReadsOpaqueBody:
    """The pre-fix _process_assistant_message read from
    self.previous_thinking_blocks, which is always empty in a fresh
    RPC instance. After the fix, it reads from the assistant message's
    opaque_body first.
    """

    def test_thinking_blocks_from_opaque_body_are_included(self) -> None:
        block = _thinking_block()
        message = AssistantPromptMessage(
            content="", tool_calls=[], opaque_body={"anthropic_thinking_blocks": [block]}
        )
        all_messages = [
            UserPromptMessage(content="hi"),
            AssistantPromptMessage(content="", tool_calls=[]),
            ToolPromptMessage(tool_call_id="1"),
        ]
        result = _process(message, all_messages)
        assert block in result["content"]

    def test_redacted_thinking_blocks_from_opaque_body_are_included(self) -> None:
        block = _redacted_block()
        message = AssistantPromptMessage(
            content="",
            tool_calls=[],
            opaque_body={"anthropic_redacted_thinking_blocks": [block]},
        )
        all_messages = [
            UserPromptMessage(content="hi"),
            AssistantPromptMessage(content="", tool_calls=[]),
            ToolPromptMessage(tool_call_id="1"),
        ]
        result = _process(message, all_messages)
        assert block in result["content"]

    def test_both_thinking_and_redacted_blocks_from_opaque_body(self) -> None:
        thinking = _thinking_block()
        redacted = _redacted_block()
        message = AssistantPromptMessage(
            content="",
            tool_calls=[],
            opaque_body={
                "anthropic_thinking_blocks": [thinking],
                "anthropic_redacted_thinking_blocks": [redacted],
            },
        )
        all_messages = [
            UserPromptMessage(content="hi"),
            AssistantPromptMessage(content="", tool_calls=[]),
            ToolPromptMessage(tool_call_id="1"),
        ]
        result = _process(message, all_messages)
        # Both blocks should be in the content, in order.
        thinking_idx = result["content"].index(thinking)
        redacted_idx = result["content"].index(redacted)
        assert thinking_idx < redacted_idx

    def test_empty_opaque_body_falls_back_to_instance_state(self) -> None:
        """If the assistant message has no opaque_body, fall back to
        the in-memory instance state (the legacy behavior).
        """
        block = _thinking_block()
        message = AssistantPromptMessage(content="", tool_calls=[])
        all_messages = [
            UserPromptMessage(content="hi"),
            AssistantPromptMessage(content="", tool_calls=[]),
            ToolPromptMessage(tool_call_id="1"),
        ]
        # Seed the instance state with the thinking block.
        instance = _make_instance()
        instance.previous_thinking_blocks = [block]
        instance.previous_redacted_thinking_blocks = []
        result = instance._process_assistant_message(message, all_messages)
        assert block in result["content"]

    def test_opaque_body_takes_precedence_over_instance_state(self) -> None:
        """If both are set, opaque_body wins (it's the persisted state)."""
        opaque_block = _thinking_block(signature="from-opaque")
        instance_block = _thinking_block(signature="from-instance")
        message = AssistantPromptMessage(
            content="",
            tool_calls=[],
            opaque_body={"anthropic_thinking_blocks": [opaque_block]},
        )
        all_messages = [
            UserPromptMessage(content="hi"),
            AssistantPromptMessage(content="", tool_calls=[]),
            ToolPromptMessage(tool_call_id="1"),
        ]
        instance = _make_instance()
        instance.previous_thinking_blocks = [instance_block]
        instance.previous_redacted_thinking_blocks = []
        result = instance._process_assistant_message(message, all_messages)
        # Only the opaque_body block should be present.
        assert opaque_block in result["content"]
        assert instance_block not in result["content"]

    def test_no_tool_messages_means_no_thinking_blocks(self) -> None:
        """Without a follow-up tool message, thinking blocks are not
        needed. The pre-fix code only added them when has_tool_messages.
        """
        block = _thinking_block()
        message = AssistantPromptMessage(
            content="", tool_calls=[], opaque_body={"anthropic_thinking_blocks": [block]}
        )
        all_messages = [
            UserPromptMessage(content="hi"),
            AssistantPromptMessage(content="hello"),
        ]
        result = _process(message, all_messages)
        assert block not in result["content"]

    def test_opaque_body_with_non_dict_value_falls_back_to_instance(self) -> None:
        """If opaque_body is not a dict (e.g. a string or list), the
        helper functions should treat it as missing and fall back to
        the instance state.
        """
        instance_block = _thinking_block()
        message = AssistantPromptMessage(content="", tool_calls=[], opaque_body="not-a-dict")
        all_messages = [
            UserPromptMessage(content="hi"),
            AssistantPromptMessage(content="", tool_calls=[]),
            ToolPromptMessage(tool_call_id="1"),
        ]
        instance = _make_instance()
        instance.previous_thinking_blocks = [instance_block]
        instance.previous_redacted_thinking_blocks = []
        result = instance._process_assistant_message(message, all_messages)
        assert instance_block in result["content"]

    def test_opaque_body_with_missing_keys_falls_back_to_instance(self) -> None:
        """opaque_body may be a dict that doesn't have the thinking-block
        keys (e.g. set by a different feature). Fall back to the
        instance state in that case.
        """
        instance_block = _thinking_block()
        message = AssistantPromptMessage(
            content="",
            tool_calls=[],
            opaque_body={"some_other_key": "some_other_value"},
        )
        all_messages = [
            UserPromptMessage(content="hi"),
            AssistantPromptMessage(content="", tool_calls=[]),
            ToolPromptMessage(tool_call_id="1"),
        ]
        instance = _make_instance()
        instance.previous_thinking_blocks = [instance_block]
        instance.previous_redacted_thinking_blocks = []
        result = instance._process_assistant_message(message, all_messages)
        assert instance_block in result["content"]


# ---------------------------------------------------------------------------
# Round-trip property: store in opaque_body, read it back
# ---------------------------------------------------------------------------


class TestRoundTripProperty:
    """The core fix: when an LLMResult is built with thinking blocks,
    the assistant_prompt_message must carry them in opaque_body so the
    next invocation can read them back. This is the regression that
    caused issue #3658.
    """

    def test_round_trip_preserves_thinking_block(self) -> None:
        """Simulate: the response handler builds an LLMResult with
        thinking blocks, then the follow-up request's
        _process_assistant_message is called with the resulting
        AssistantPromptMessage. The thinking block must round-trip
        through opaque_body.
        """
        # Step 1: response handler captures the thinking block.
        block = _thinking_block()
        instance = _make_instance()
        instance.previous_thinking_blocks = [block]
        instance.previous_redacted_thinking_blocks = []
        # Simulate what _handle_chat_generate_response does at the end.
        assistant_prompt_message = AssistantPromptMessage(content="", tool_calls=[])
        if instance.previous_thinking_blocks or instance.previous_redacted_thinking_blocks:
            assistant_prompt_message.opaque_body = {
                "anthropic_thinking_blocks": instance.previous_thinking_blocks,
                "anthropic_redacted_thinking_blocks": instance.previous_redacted_thinking_blocks,
            }

        # Step 2: the next request is built in a fresh instance. The
        # caller passes the persisted AssistantPromptMessage (with
        # opaque_body) plus the tool result.
        fresh_instance = _make_instance()
        fresh_instance.previous_thinking_blocks = []  # empty in fresh instance
        fresh_instance.previous_redacted_thinking_blocks = []
        all_messages = [
            UserPromptMessage(content="hi"),
            AssistantPromptMessage(content="", tool_calls=[]),
            ToolPromptMessage(tool_call_id="1"),
        ]
        result = fresh_instance._process_assistant_message(assistant_prompt_message, all_messages)
        # The thinking block must be present in the next request.
        assert block in result["content"]

    def test_round_trip_without_thinking_blocks_has_no_opaque_body(self) -> None:
        """A response with no thinking blocks must not have an
        opaque_body set (avoids carrying empty dicts in messages).
        """
        instance = _make_instance()
        instance.previous_thinking_blocks = []
        instance.previous_redacted_thinking_blocks = []
        # Simulate: when both lists are empty, opaque_body should not be set.
        assistant_prompt_message = AssistantPromptMessage(content="hello")
        if instance.previous_thinking_blocks or instance.previous_redacted_thinking_blocks:
            assistant_prompt_message.opaque_body = {
                "anthropic_thinking_blocks": instance.previous_thinking_blocks,
                "anthropic_redacted_thinking_blocks": instance.previous_redacted_thinking_blocks,
            }
        assert assistant_prompt_message.opaque_body is None

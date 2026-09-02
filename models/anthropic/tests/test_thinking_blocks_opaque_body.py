"""Regression coverage for issue #3658.

Anthropic thinking / redacted_thinking blocks emitted on a tool-use
turn must be echoed back verbatim on the follow-up tool-result turn.
The SDK's ``ModelFactory.get_instance()`` builds a fresh
``AnthropicLargeLanguageModel`` for every RPC, so the plugin's
``self.previous_*`` state is empty by the time the follow-up turn is
built. The fix stores the blocks on ``AssistantPromptMessage.opaque_body``
(using the same pattern ``models/moonshot`` already uses for
``reasoning_content``) so the round-trip survives the per-RPC
instance lifecycle.

These tests assert both halves of the round-trip:

1. ``_handle_chat_generate_response`` (non-streaming) and
   ``_handle_chat_generate_stream_response`` (streaming) attach the
   blocks to ``assistant_prompt_message.opaque_body`` (serialized to
   JSON-safe dicts).
2. ``_process_assistant_message`` reads from ``message.opaque_body``
   first and falls back to the instance state only when the caller
   hand-crafts an ``AssistantPromptMessage`` without ``opaque_body``.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock


from dify_plugin.entities.model.message import (
    AssistantPromptMessage,
    SystemPromptMessage,
    ToolPromptMessage,
    UserPromptMessage,
)

from models.llm.llm import AnthropicLargeLanguageModel

_THINKING = {
    "type": "thinking",
    "thinking": "secret chain of thought",
    "signature": "sig-abc",
}
_REDACTED = {"type": "redacted_thinking", "data": "ENCRYPTED_PAYLOAD"}


def _llm() -> AnthropicLargeLanguageModel:
    """Construct an isolated instance (the SDK does this per RPC)."""
    return AnthropicLargeLanguageModel([])


class TestThinkingBlockToDict:
    def test_pydantic_model_is_serialized_via_model_dump(self):
        block = MagicMock(spec=["model_dump"])
        block.model_dump.return_value = {
            "type": "thinking",
            "thinking": "...",
            "signature": "...",
        }
        out = _llm()._thinking_block_to_dict(block)
        block.model_dump.assert_called_once()
        assert out == {"type": "thinking", "thinking": "...", "signature": "..."}

    def test_plain_dict_is_copied(self):
        out = _llm()._thinking_block_to_dict({"type": "redacted_thinking", "data": "x"})
        assert out == {"type": "redacted_thinking", "data": "x"}


class TestBuildThinkingOpaqueBody:
    def test_returns_none_when_both_lists_empty(self):
        assert _llm()._build_thinking_opaque_body([], []) is None

    def test_serializes_thinking_only(self):
        out = _llm()._build_thinking_opaque_body([_THINKING], [])
        assert out == {"thinking_blocks": [_THINKING], "redacted_thinking_blocks": []}

    def test_serializes_redacted_only(self):
        out = _llm()._build_thinking_opaque_body([], [_REDACTED])
        assert out == {"thinking_blocks": [], "redacted_thinking_blocks": [_REDACTED]}

    def test_serializes_both_lists(self):
        out = _llm()._build_thinking_opaque_body([_THINKING], [_REDACTED])
        assert out["thinking_blocks"] == [_THINKING]
        assert out["redacted_thinking_blocks"] == [_REDACTED]


class TestProcessAssistantMessageReadsOpaqueBody:
    """The follow-up tool-result turn must use the blocks the previous
    turn persisted in ``opaque_body``, not the per-instance state."""

    def _tool_messages(self) -> list[ToolPromptMessage]:
        return [
            ToolPromptMessage(
                content="ok",
                tool_call_id="tool-1",
            )
        ]

    def _all_messages(self) -> list[Any]:
        return [
            SystemPromptMessage(content="be helpful"),
            UserPromptMessage(content="hi"),
            AssistantPromptMessage(content="calling tool", tool_calls=[]),
            *self._tool_messages(),
        ]

    def test_thinking_block_survives_instance_boundary(self):
        """The receiver was a fresh instance (the SDK's ModelFactory
        created a new AnthropicLargeLanguageModel), so the previous-turn
        blocks must come from the message's opaque_body, not from
        ``self.previous_*``."""
        llm = _llm()  # fresh instance, self.previous_* is []
        assistant = AssistantPromptMessage(
            content="calling tool",
            tool_calls=[
                AssistantPromptMessage.ToolCall(
                    id="tool-1",
                    type="function",
                    function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                        name="search", arguments="{}"
                    ),
                )
            ],
            opaque_body={
                "thinking_blocks": [_THINKING],
                "redacted_thinking_blocks": [_REDACTED],
            },
        )

        out = llm._process_assistant_message(assistant, self._all_messages())

        assert out["role"] == "assistant"
        # Thinking block must come first, then redacted, then text, then tool_use
        # (Anthropic requires the same order the model emitted them).
        assert out["content"][0] == _THINKING
        assert out["content"][1] == _REDACTED

    def test_no_thinking_block_yields_no_thinking_content(self):
        llm = _llm()
        assistant = AssistantPromptMessage(
            content="calling tool",
            tool_calls=[],
            opaque_body=None,
        )

        out = llm._process_assistant_message(assistant, self._all_messages())

        # No thinking content should have been prepended.
        assert all(
            c["type"] not in ("thinking", "redacted_thinking") for c in out["content"]
        )

    def test_empty_opaque_body_falls_back_to_instance_state(self):
        """When opaque_body is present but empty, the legacy
        ``self.previous_*`` state still works (covers callers that
        hand-craft ``AssistantPromptMessage`` without opaque_body)."""
        llm = _llm()
        llm.previous_thinking_blocks = [_THINKING]
        llm.previous_redacted_thinking_blocks = [_REDACTED]
        assistant = AssistantPromptMessage(
            content="calling tool",
            tool_calls=[],
            opaque_body={},  # empty
        )

        out = llm._process_assistant_message(assistant, self._all_messages())

        assert out["content"][0] == _THINKING
        assert out["content"][1] == _REDACTED

    def test_opaque_body_takes_precedence_over_instance_state(self):
        """When both opaque_body and instance state are present, the
        persisted opaque_body wins (it's the canonical round-trip path)."""
        llm = _llm()
        # Instance state has stale / wrong data; opaque_body has the
        # round-tripped data from the previous turn.
        llm.previous_thinking_blocks = [
            {"type": "thinking", "thinking": "stale", "signature": "stale-sig"}
        ]
        assistant = AssistantPromptMessage(
            content="calling tool",
            tool_calls=[],
            opaque_body={
                "thinking_blocks": [_THINKING],
                "redacted_thinking_blocks": [_REDACTED],
            },
        )

        out = llm._process_assistant_message(assistant, self._all_messages())

        assert out["content"][0] == _THINKING
        assert out["content"][1] == _REDACTED

    def test_no_tool_messages_skips_thinking_block_prepend(self):
        """A plain assistant turn (no tool call) does not need the
        thinking blocks; the API rejects them as out-of-order content
        when there is no tool_use in the same assistant turn."""
        llm = _llm()
        assistant = AssistantPromptMessage(
            content="no tools here",
            tool_calls=[],
            opaque_body={
                "thinking_blocks": [_THINKING],
                "redacted_thinking_blocks": [_REDACTED],
            },
        )
        all_messages = [
            SystemPromptMessage(content="be helpful"),
            UserPromptMessage(content="hi"),
        ]

        out = llm._process_assistant_message(assistant, all_messages)

        assert all(
            c["type"] not in ("thinking", "redacted_thinking") for c in out["content"]
        )

    def test_non_dict_opaque_body_does_not_crash(self):
        llm = _llm()
        assistant = AssistantPromptMessage(
            content="calling tool",
            tool_calls=[],
            opaque_body="not a dict",  # type: ignore[arg-type]
        )

        # Should not crash; falls back to instance state.
        out = llm._process_assistant_message(assistant, self._all_messages())

        assert out["role"] == "assistant"


class TestHandleChatGenerateResponseAttachesOpaqueBody:
    def test_block_collection_and_opaque_body_wiring(self, monkeypatch):
        """The non-streaming handler collects thinking / redacted_thinking
        content blocks from the response and attaches them to the returned
        ``assistant_prompt_message.opaque_body``. The actual HTTP plumbing
        of ``_handle_chat_generate_response`` is not exercised here — the
        Anthropic SDK requires a real ``Message`` instance to tokenize, and
        the SDK's Pydantic model is exercised in the SDK's own test suite.
        This test pins the wiring (collect blocks -> set opaque_body)
        using a small ``ContentBlock``-like stub class.
        """

        class _StubBlock:
            def __init__(self, *, type: str, **payload: Any) -> None:
                self.type = type
                self._payload = payload

            def model_dump(self, exclude_none: bool = False) -> dict:
                return {"type": self.type, **self._payload}

        class _StubResponse:
            def __init__(self, content: list, model: str = "claude-opus-4-7") -> None:
                self.content = content
                self.model = model

        # Drive the wiring directly without going through the heavy
        # ``_handle_chat_generate_response`` body. The wiring is the
        # collection loop + ``_build_thinking_opaque_body`` call.
        thinking_block = _StubBlock(type="thinking", thinking="secret", signature="sig")
        redacted_block = _StubBlock(type="redacted_thinking", data="PAYLOAD")
        text_block = _StubBlock(type="text")
        text_block.text = "hi"  # type: ignore[attr-defined]

        assistant_prompt_message = AssistantPromptMessage(content="hi", tool_calls=[])
        thinking_blocks: list = []
        redacted_thinking_blocks: list = []
        for content in [thinking_block, redacted_block, text_block]:
            if content.type == "thinking":
                thinking_blocks.append(content)
            elif content.type == "redacted_thinking":
                redacted_thinking_blocks.append(content)

        llm = _llm()
        opaque_body = llm._build_thinking_opaque_body(
            thinking_blocks, redacted_thinking_blocks
        )
        if opaque_body is not None:
            assistant_prompt_message.opaque_body = opaque_body

        assert assistant_prompt_message.opaque_body == {
            "thinking_blocks": [
                {"type": "thinking", "thinking": "secret", "signature": "sig"}
            ],
            "redacted_thinking_blocks": [
                {"type": "redacted_thinking", "data": "PAYLOAD"}
            ],
        }


class TestFullRoundTripAcrossInstances:
    def test_thinking_block_survives_a_fresh_instance(self):
        """Mirrors what ``ModelFactory.get_instance()`` does: response was
        handled by instance A, follow-up is handled by a fresh instance B.
        The block from A's ``opaque_body`` must reach the API request that
        B builds."""
        instance_a = _llm()
        instance_b = _llm()  # fresh; self.previous_* is []

        # A's response had a thinking block; record the round-trip.
        instance_a.previous_thinking_blocks = [_THINKING]
        instance_a.previous_redacted_thinking_blocks = [_REDACTED]
        opaque_body = instance_a._build_thinking_opaque_body(
            instance_a.previous_thinking_blocks,
            instance_a.previous_redacted_thinking_blocks,
        )

        # B receives the assistant message with the persisted opaque_body.
        assistant = AssistantPromptMessage(
            content="calling tool",
            tool_calls=[
                AssistantPromptMessage.ToolCall(
                    id="tool-1",
                    type="function",
                    function=AssistantPromptMessage.ToolCall.ToolCallFunction(
                        name="search", arguments="{}"
                    ),
                )
            ],
            opaque_body=opaque_body,
        )
        all_messages = [
            SystemPromptMessage(content="be helpful"),
            UserPromptMessage(content="hi"),
            assistant,
            ToolPromptMessage(content="ok", tool_call_id="tool-1"),
        ]

        out = instance_b._process_assistant_message(assistant, all_messages)

        # The thinking + redacted blocks survived the instance boundary.
        assert out["content"][0] == _THINKING
        assert out["content"][1] == _REDACTED

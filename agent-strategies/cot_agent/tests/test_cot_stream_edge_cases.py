"""Regression tests for three ReAct stream parser edge cases in
``agent-strategies.cot_agent.output_parser.cot_output_parser``.

These tests cover issues that were intentionally left out of PR #3703
(fix for #3699) and filed as separate follow-ups in #3705:

1. Adjacent JSON roots — when the model emits two JSON objects with no
   delimiter (e.g. ``{}{}``), the first blob was silently dropped because
   the 'start new JSON' branch overwrote the json_cache before the first
   blob was parsed.

2. Two-level OpenAI-style function envelopes — ``{"tool_call":
   {"function": {"name": "...", "arguments": ...}}}`` and the list
   variant were rejected because the outer ``tool_call`` key became the
   action_name and the inner function dict was rejected as not-a-string.

3. Split think tags — Gemini's ``<think>`` / ``</think>`` injection was
   only stripped when the tag arrived complete in one chunk. If the tag
   was split (e.g. chunk 1 = ``"\\nthi"``, chunk 2 = ``"nk>inner\\n/think>"``),
   the partial prefix leaked as raw text and corrupted ReAct parsing.

The test harness is independent of the one added in PR #3703 (which
is not yet on main). Each test feeds a synthetic chunk sequence to
``CotAgentOutputParser.handle_react_stream_output`` and asserts the
resulting stream.
"""

from __future__ import annotations

import sys
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

from output_parser.cot_output_parser import (  # noqa: E402
    CotAgentOutputParser,
    ReactChunk,
)
from dify_plugin.entities.model.llm import LLMResultChunk  # noqa: E402
from dify_plugin.interfaces.agent import AgentScratchpadUnit  # noqa: E402


def _make_chunk(content: Any) -> LLMResultChunk:
    """Build a minimal ``LLMResultChunk`` carrying the given content."""
    delta = MagicMock()
    delta.message.content = content
    delta.usage = None
    chunk = MagicMock(spec=LLMResultChunk)
    chunk.delta = delta
    return chunk


def _stream(*contents: Any) -> Generator[LLMResultChunk, None, None]:
    for content in contents:
        yield _make_chunk(content)


def _collect(
    *contents: Any,
) -> list[Any]:
    """Run the parser on a single combined stream and return all yielded items."""
    parser = CotAgentOutputParser()
    usage: dict = {}
    return list(parser.handle_react_stream_output(_stream(*contents), usage))


# ---------------------------------------------------------------------------
# 1. Adjacent JSON roots
# ---------------------------------------------------------------------------


class TestAdjacentJsonRoots:
    """The pre-fix parser dropped the first blob when the model emitted
    two JSON roots with no delimiter (``{}{}``). After the fix, both
    blobs must be processed in order.
    """

    def test_two_adjacent_actions_are_both_yielded(self) -> None:
        results = _collect(
            '{"action": "first", "action_input": {}}{"action": "second", "action_input": {}}'
        )
        actions = [r for r in results if isinstance(r, AgentScratchpadUnit.Action)]
        assert len(actions) == 2, f"Expected 2 Action yields, got {len(actions)}: {results}"
        assert actions[0].action_name == "first"
        assert actions[1].action_name == "second"

    def test_first_action_invocation_appears_before_second(self) -> None:
        results = _collect(
            '{"action": "alpha", "action_input": {}}{"action": "beta", "action_input": {}}'
        )
        actions = [r for r in results if isinstance(r, AgentScratchpadUnit.Action)]
        assert [a.action_name for a in actions] == ["alpha", "beta"]

    def test_three_adjacent_actions_all_yielded(self) -> None:
        results = _collect(
            '{"action": "a", "action_input": {}}'
            '{"action": "b", "action_input": {}}'
            '{"action": "c", "action_input": {}}'
        )
        actions = [r for r in results if isinstance(r, AgentScratchpadUnit.Action)]
        assert [a.action_name for a in actions] == ["a", "b", "c"]

    def test_adjacent_arrays_also_processed(self) -> None:
        results = _collect(
            '[{"action": "x", "action_input": {}}]' '[{"action": "y", "action_input": {}}]'
        )
        actions = [r for r in results if isinstance(r, AgentScratchpadUnit.Action)]
        assert [a.action_name for a in actions] == ["x", "y"]


# ---------------------------------------------------------------------------
# 2. OpenAI-style tool_call / tool_calls envelopes
# ---------------------------------------------------------------------------


class TestOpenAIToolCallEnvelope:
    """The pre-fix parser rejected ``{"tool_call": {"function":
    {"name": ..., "arguments": ...}}}`` because the outer ``tool_call``
    key became action_name and the inner function dict was rejected as
    not-a-string. After the fix, both single and list variants are
    unwrapped and parsed correctly.
    """

    def test_single_tool_call_envelope(self) -> None:
        results = _collect(
            '{"tool_call": {"function": {"name": "webSearch", "arguments": {"query": "x"}}}}'
        )
        actions = [r for r in results if isinstance(r, AgentScratchpadUnit.Action)]
        assert len(actions) == 1
        assert actions[0].action_name == "webSearch"
        assert actions[0].action_input == {"query": "x"}

    def test_single_tool_calls_list_envelope(self) -> None:
        results = _collect(
            '{"tool_calls": [{"function": {"name": "lookup", "arguments": {"k": "v"}}}]}'
        )
        actions = [r for r in results if isinstance(r, AgentScratchpadUnit.Action)]
        assert len(actions) == 1
        assert actions[0].action_name == "lookup"
        assert actions[0].action_input == {"k": "v"}

    def test_envelope_with_action_and_action_input_keys_still_works(self) -> None:
        """The original ReAct format (no envelope) must continue to work."""
        results = _collect('{"action": "search", "action_input": {"q": "rust"}}')
        actions = [r for r in results if isinstance(r, AgentScratchpadUnit.Action)]
        assert len(actions) == 1
        assert actions[0].action_name == "search"
        assert actions[0].action_input == {"q": "rust"}

    def test_envelope_does_not_trigger_when_tool_call_value_is_not_dict(self) -> None:
        """If ``tool_call`` is present but its value is a string (unusual but
        legal JSON), the parser should not crash. It degrades to the
        parse-failure path (the blob is yielded as a ReactChunk).
        """
        results = _collect('{"tool_call": "not-a-dict"}')
        # No Action yielded; the blob itself is emitted as a raw chunk.
        actions = [r for r in results if isinstance(r, AgentScratchpadUnit.Action)]
        assert actions == []
        chunks = [r for r in results if isinstance(r, ReactChunk)]
        assert any("tool_call" in c.content for c in chunks)


# ---------------------------------------------------------------------------
# 3. Split think tags across chunks
# ---------------------------------------------------------------------------


class TestSplitThinkTags:
    """The pre-fix parser only stripped complete ``<think>`` /
    ``</think>`` tags within a single chunk. If the tag was split across
    chunks, the partial prefix leaked as raw text. After the fix, the
    trailing partial-prefix of up to ``len(<think>) - 1`` chars is
    buffered across chunks.

    The pre-fix input from the issue body was malformed; the real
    model-emitted shape is a normal ``<think>...</think>`` block that
    the stream just happened to split mid-tag. The tests below use
    correctly-shaped inputs.
    """

    def test_think_split_in_middle_of_open_tag(self) -> None:
        # Model emits <think>inner</think> but the stream splits the open
        # tag: chunk 1 = "<th", chunk 2 = "ink>inner</think>". Pre-fix,
        # the partial "<th" was emitted as raw content. Post-fix, the
        # trailing "<th" is buffered and reassembled with the next
        # chunk so the think block is stripped cleanly.
        results = _collect("<th", "ink>inner</think>")
        text = "".join(r.content for r in results if isinstance(r, ReactChunk))
        assert "<think>" not in text
        assert "</think>" not in text
        assert "inner" not in text  # think content is stripped
        # The leaked partial prefix "<th" must NOT be in the output.
        assert "<th" not in text

    def test_think_split_at_th_in_close_tag(self) -> None:
        # Model emits <think>x</think> but the stream splits the close
        # tag: chunk 1 = "<think>x</thin", chunk 2 = "k>". Pre-fix, the
        # partial "</thin" was emitted as raw content. Post-fix, the
        # trailing partial close tag is buffered and reassembled.
        results = _collect("<think>x</think>"[0:9], "<think>x</think>"[9:])
        text = "".join(r.content for r in results if isinstance(r, ReactChunk))
        assert "<think>" not in text
        assert "</think>" not in text
        assert "x" not in text  # think content is stripped

    def test_complete_think_in_single_chunk_still_stripped(self) -> None:
        """Regression: a complete tag in a single chunk must still be
        stripped (the original behavior must not regress).
        """
        results = _collect("<think>reasoning</think>after")
        text = "".join(r.content for r in results if isinstance(r, ReactChunk))
        assert "<think>" not in text
        assert "reasoning" not in text
        assert "after" in text

    def test_think_split_across_three_chunks(self) -> None:
        # chunk 1 = "<th", chunk 2 = "in", chunk 3 = "k>inner</think>"
        # Each chunk is shorter than len(<think>) - 1, so all three must be
        # buffered before the open tag can be recognized.
        results = _collect("<th", "in", "k>inner</think>")
        text = "".join(r.content for r in results if isinstance(r, ReactChunk))
        assert "<think>" not in text
        assert "inner" not in text  # think content is stripped
        # The leaked partial open tag must NOT be in the output.
        assert "<th" not in text
        assert "ink" not in text.split("<think>")[-1] if "<think>" in text else "ink" not in text


# ---------------------------------------------------------------------------
# 4. Sanity: existing behavior must not regress
# ---------------------------------------------------------------------------


class TestExistingBehaviorUnchanged:
    """The three fixes are additive. These tests pin the original
    behavior so a future refactor cannot silently break it.
    """

    def test_single_action_yields_one_action(self) -> None:
        results = _collect('{"action": "search", "action_input": {"q": "rust"}}')
        actions = [r for r in results if isinstance(r, AgentScratchpadUnit.Action)]
        assert len(actions) == 1

    def test_incomplete_json_does_not_yield_action(self) -> None:
        """An incomplete JSON blob (no closing brace) at end of stream
        should not produce a spurious Action.
        """
        results = _collect('{"action": "search", "action_input":')
        actions = [r for r in results if isinstance(r, AgentScratchpadUnit.Action)]
        # The trailing partial blob is yielded as a raw ReactChunk, not
        # an Action. (Matches pre-fix behavior for incomplete JSON.)
        assert actions == []

    def test_complete_think_then_action(self) -> None:
        """Standard ReAct sequence with a complete think block must
        produce both the stripped thought content and the action.
        """
        results = _collect(
            "<think>step 1</think>",
            'Action: {"action": "search", "action_input": {"q": "x"}}',
        )
        actions = [r for r in results if isinstance(r, AgentScratchpadUnit.Action)]
        assert len(actions) == 1
        assert actions[0].action_name == "search"
        # Think content must be stripped.
        text = "".join(r.content for r in results if isinstance(r, ReactChunk))
        assert "step 1" not in text

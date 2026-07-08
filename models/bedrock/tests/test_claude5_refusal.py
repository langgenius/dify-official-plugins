"""Unit tests for Claude 5 refusal detection and fallback stream wrapper."""
import importlib

import pytest

llm_mod = importlib.import_module("models.llm.llm")

from dify_plugin.entities.model.llm import LLMResultChunk, LLMResultChunkDelta
from dify_plugin.entities.model.message import AssistantPromptMessage

BedrockLLM = llm_mod.BedrockLargeLanguageModel


def _chunk(content="", finish_reason=None):
    return LLMResultChunk(
        model="global.anthropic.claude-fable-5",
        prompt_messages=[],
        delta=LLMResultChunkDelta(
            index=0,
            message=AssistantPromptMessage(content=content),
            finish_reason=finish_reason,
        ),
    )


class TestRefusalDetection:
    def test_content_filtered_is_refusal(self):
        # Converse StopReason enum has no "refusal" — classifier blocks are
        # expected to surface as content_filtered (live-verified enum)
        assert BedrockLLM._is_claude5_refusal("content_filtered", None)

    def test_native_refusal_string_still_detected(self):
        assert BedrockLLM._is_claude5_refusal("refusal", None)

    def test_stop_details_signal(self):
        assert BedrockLLM._is_claude5_refusal(
            "end_turn", {"stop_details": {"category": "cyber"}}
        )

    def test_normal_completion_not_refusal(self):
        # Live-verified: stop_details is null on normal completion
        assert not BedrockLLM._is_claude5_refusal("end_turn", {"stop_details": None})
        assert not BedrockLLM._is_claude5_refusal("end_turn", None)
        assert not BedrockLLM._is_claude5_refusal("tool_use", {})


class TestExtractRefusalDetail:
    def test_reads_additional_model_response_fields(self):
        response = {
            "stopReason": "content_filtered",
            "additionalModelResponseFields": {
                "stop_details": {"category": "cyber", "explanation": "blocked"}
            },
        }
        detail = BedrockLLM._extract_refusal_detail(response)
        assert "cyber" in detail

    def test_missing_details_returns_placeholder(self):
        detail = BedrockLLM._extract_refusal_detail({"stopReason": "content_filtered"})
        assert isinstance(detail, str) and detail  # non-empty, never raises


class TestWrapClaude5Stream:
    def test_passthrough_when_no_refusal(self):
        inner = iter([_chunk("hello"), _chunk("", finish_reason="end_turn")])
        out = list(BedrockLLM._wrap_claude5_stream(inner, None, "global.anthropic.claude-fable-5"))
        assert [c.delta.message.content for c in out] == ["hello", ""]

    @pytest.mark.parametrize("reason", ["refusal", "content_filtered"])
    def test_pre_content_refusal_restarts_on_fallback(self, reason):
        inner = iter([_chunk("", finish_reason=reason)])
        fallback_chunks = [_chunk("fallback answer"), _chunk("", finish_reason="end_turn")]
        out = list(BedrockLLM._wrap_claude5_stream(
            inner, lambda: iter(fallback_chunks), "global.anthropic.claude-fable-5"
        ))
        assert out == fallback_chunks  # refusal chunk swallowed, fallback streamed

    def test_pre_content_refusal_without_fallback_raises(self):
        inner = iter([_chunk("", finish_reason="content_filtered")])
        with pytest.raises(llm_mod.InvokeError, match="refus"):
            list(BedrockLLM._wrap_claude5_stream(inner, None, "global.anthropic.claude-fable-5"))

    def test_mid_stream_refusal_raises_even_with_fallback(self):
        inner = iter([_chunk("partial"), _chunk("", finish_reason="content_filtered")])
        gen = BedrockLLM._wrap_claude5_stream(
            inner, lambda: iter([_chunk("never")]), "global.anthropic.claude-fable-5"
        )
        assert next(gen).delta.message.content == "partial"
        with pytest.raises(llm_mod.InvokeError, match="refus"):
            list(gen)

    def test_thinking_content_counts_as_content(self):
        # <think> text is user-visible; a refusal after it is mid-stream
        inner = iter([_chunk("<think>\nreasoning"), _chunk("", finish_reason="content_filtered")])
        gen = BedrockLLM._wrap_claude5_stream(
            inner, lambda: iter([_chunk("never")]), "global.anthropic.claude-fable-5"
        )
        next(gen)
        with pytest.raises(llm_mod.InvokeError):
            list(gen)


class TestNonStreamReasoningContent:
    def test_reasoning_block_does_not_crash(self):
        response = {
            "stopReason": "end_turn",
            "output": {"message": {"content": [
                {"reasoningContent": {"reasoningText": {"text": "thinking...", "signature": "sig"}}},
                {"text": "The answer is 391."},
            ]}},
            "usage": {"inputTokens": 10, "outputTokens": 20},
        }
        # _handle_converse_response calls _calc_response_usage (needs real
        # credentials plumbing) — test the block-filtering logic directly by
        # invoking the method with a minimal fake and asserting no exception
        # up to the usage call, or refactor the filtering into a static
        # helper _fold_reasoning_content(content) and test that:
        content, prefix = BedrockLLM._fold_reasoning_content(
            response["output"]["message"]["content"]
        )
        assert prefix.startswith("<think>")
        assert all("reasoningContent" not in b for b in content)

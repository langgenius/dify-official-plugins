import os
import sys

from google.genai import types

try:
    from models.llm.llm import VertexAiLargeLanguageModel
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from models.llm.llm import VertexAiLargeLanguageModel


def test_returns_zero_zero_when_metadata_is_none():
    assert VertexAiLargeLanguageModel._calculate_tokens_from_usage_metadata(None) == (0, 0)


def test_reads_prompt_token_count_directly():
    """
    ``prompt_token_count`` is Google's authoritative aggregate (includes cached
    tokens on cache hits and any future modalities), so we use it directly
    rather than summing per-modality details.
    """
    meta = types.GenerateContentResponseUsageMetadata(
        prompt_token_count=24,
        prompt_tokens_details=[
            types.ModalityTokenCount(modality=types.MediaModality.TEXT, token_count=18),
            types.ModalityTokenCount(modality=types.MediaModality.DOCUMENT, token_count=6),
        ],
        candidates_token_count=58,
        thoughts_token_count=120,
        total_token_count=202,
    )
    prompt_tokens, completion_tokens = VertexAiLargeLanguageModel._calculate_tokens_from_usage_metadata(meta)
    assert prompt_tokens == 24
    assert completion_tokens == 178  # 58 candidates + 120 thoughts; see SKU split rationale in docstring


def test_zero_token_reply_is_preserved_not_treated_as_missing():
    """
    Caller contract: a legitimate zero-token reply (e.g. function-call-only
    response) should round-trip as (0, 0). Callers branch on
    ``usage_metadata is None`` to decide fallback, not on the returned zero.
    """
    meta = types.GenerateContentResponseUsageMetadata(
        prompt_token_count=0,
        prompt_tokens_details=None,
        candidates_token_count=0,
        thoughts_token_count=None,
        total_token_count=0,
    )
    assert VertexAiLargeLanguageModel._calculate_tokens_from_usage_metadata(meta) == (0, 0)


def test_handles_missing_thoughts_token_count():
    meta = types.GenerateContentResponseUsageMetadata(
        prompt_token_count=10,
        prompt_tokens_details=None,
        candidates_token_count=5,
        thoughts_token_count=None,
        total_token_count=15,
    )
    prompt_tokens, completion_tokens = VertexAiLargeLanguageModel._calculate_tokens_from_usage_metadata(meta)
    assert prompt_tokens == 10
    assert completion_tokens == 5

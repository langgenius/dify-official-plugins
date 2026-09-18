"""Offline unit tests for the gemini plugin performance layer.

Covers, without any network access or API key:

- genai.Client connection-pool reuse (LLM + embedding module caches)
- thread-safe in-memory FileCache (concurrency, expiry, eviction)
- local GPT-2 token counting in the embedding text splitter
- prompt_token_count fallback in the usage-metrics mapping

These tests are intentionally NOT marked ``live`` so they run in CI without
a GEMINI_API_KEY.
"""

import threading
import time
from types import SimpleNamespace

from models.llm import llm as gemini_llm
from models.llm.utils import FileCache
from models.text_embedding.text_embedding import (
    GeminiTextEmbeddingModel,
    _genai_emb_client_cache,
    _get_genai_client as _get_emb_client,
)


def _boom(*args, **kwargs):
    raise AssertionError("API token-counting round-trip attempted in splitter")


# ---------------------------------------------------------------------------
# LLM client cache
# ---------------------------------------------------------------------------


def test_llm_client_cache_returns_same_instance_for_same_creds():
    c1 = gemini_llm._get_genai_client("key-a", None)
    c2 = gemini_llm._get_genai_client("key-a", None)
    assert c1 is c2
    assert len(gemini_llm._genai_client_cache) == 1


def test_llm_client_cache_distinct_keys_distinct_clients():
    c1 = gemini_llm._get_genai_client("key-a", None)
    c2 = gemini_llm._get_genai_client("key-b", None)
    c3 = gemini_llm._get_genai_client("key-a", "https://alt.example")
    assert c1 is not c2
    assert c1 is not c3
    assert len(gemini_llm._genai_client_cache) == 3


def test_llm_client_helper_builds_one_client_per_credential(monkeypatch):
    """The LLM helper must construct exactly one genai.Client per credential
    tuple, however many times it is called."""
    constructions = []
    real_client_cls = gemini_llm.genai.Client

    class _CountingClient(real_client_cls):
        def __init__(self, *args, **kwargs):
            constructions.append(kwargs)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(gemini_llm.genai, "Client", _CountingClient)

    client = gemini_llm._get_genai_client("key-a", None)
    again = gemini_llm._get_genai_client("key-a", None)
    assert client is again
    assert len(constructions) == 1
    assert constructions[0]["api_key"] == "key-a"


def test_llm_generate_sources_no_longer_build_raw_clients():
    """Regression guard: the hot paths must not construct genai.Client
    inline anymore (validate_credentials is the only allowed site).

    Note: this is a source-level guard scoped to the current layout; if the
    construction is refactored (e.g. through another helper), update it.
    """
    import inspect

    src = inspect.getsource(gemini_llm.GoogleLargeLanguageModel)
    raw_sites = src.count("genai.Client(")
    # _get_genai_client lives at module level, so inside the class body the
    # only acceptable remaining occurrences are in validate_credentials.
    validate_src = inspect.getsource(
        gemini_llm.GoogleLargeLanguageModel.validate_credentials
    )
    allowed = validate_src.count("genai.Client(")
    assert raw_sites == allowed, (
        f"expected only {allowed} raw genai.Client( site(s) "
        f"(validate_credentials), found {raw_sites}"
    )


# ---------------------------------------------------------------------------
# Embedding client cache
# ---------------------------------------------------------------------------


def test_emb_client_cache_identity():
    c1 = _get_emb_client("key-x")
    c2 = _get_emb_client("key-x")
    c3 = _get_emb_client("key-y")
    assert c1 is c2
    assert c1 is not c3
    assert len(_genai_emb_client_cache) == 2


def test_emb_client_cache_is_separate_from_llm_cache():
    c = gemini_llm._get_genai_client("same-key", None)
    e = _get_emb_client("same-key")
    # Same credential, but the two modules keep independent client instances.
    assert c is not e
    gemini_llm._genai_client_cache.clear()
    # Embedding cache survives the LLM cache being cleared (and vice versa).
    assert len(_genai_emb_client_cache) == 1


# ---------------------------------------------------------------------------
# FileCache
# ---------------------------------------------------------------------------


def test_filecache_setex_get_and_expiry():
    cache = FileCache()
    cache.setex("k", 60, "v")
    assert cache.exists("k")
    assert cache.get("k") == "v"

    cache.setex("expired", -1, "gone")
    assert not cache.exists("expired")
    assert cache.get("expired") is None
    assert cache.get("missing") is None


def test_filecache_concurrent_writes_no_lost_updates():
    cache = FileCache()
    n_threads, n_keys = 8, 200

    def worker(tid):
        for i in range(n_keys):
            cache.setex(f"{tid}-{i}", 60, f"v{tid}-{i}")

    threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(cache._cache) == n_threads * n_keys
    for tid in range(n_threads):
        for i in range(n_keys):
            assert cache.get(f"{tid}-{i}") == f"v{tid}-{i}"


def test_filecache_eviction_purges_only_expired_entries():
    cache = FileCache()
    for i in range(cache._EVICT_AFTER_ENTRIES + 1):
        cache.setex(f"dead-{i}", -1, "x")
    for i in range(10):
        cache.setex(f"live-{i}", 3600, f"v{i}")
    # Backdate the last eviction so the interval guard passes.
    cache._last_evict_at = time.time() - cache._EVICT_MIN_INTERVAL_SECONDS - 1
    cache.setex("alive", 60, "y")

    # Every non-expired entry survives the eviction pass.
    assert cache.get("alive") == "y"
    for i in range(10):
        assert cache.get(f"live-{i}") == f"v{i}"
    # Only the expired entries were purged.
    assert len(cache._cache) == 11
    assert not cache.exists("dead-0")


def test_filecache_concurrent_reads_during_writes():
    cache = FileCache()
    errors = []
    barrier = threading.Barrier(4)  # guarantee read/write overlap

    def writer():
        try:
            barrier.wait()
            for i in range(200):
                cache.setex(f"w-{i}", 60, str(i))
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    def reader():
        try:
            barrier.wait()
            for i in range(200):
                cache.get(f"w-{i}")
                cache.exists(f"w-{i}")
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [
        threading.Thread(target=writer),
        threading.Thread(target=reader),
        threading.Thread(target=writer),
        threading.Thread(target=reader),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []


def test_filecache_signature_back_compatible():
    # The cache_file argument is accepted (and ignored for storage) so any
    # existing instantiation keeps working.
    cache = FileCache(cache_file="/nonexistent/dir/file_cache.json")
    cache.setex("k", 60, "v")
    assert cache.get("k") == "v"


# ---------------------------------------------------------------------------
# Usage-metrics mapping: prompt_token_count fallback
# ---------------------------------------------------------------------------


def _usage(details, prompt_token_count, thoughts=0, candidates=10):
    return SimpleNamespace(
        prompt_tokens_details=details,
        prompt_token_count=prompt_token_count,
        thoughts_token_count=thoughts,
        candidates_token_count=candidates,
    )


def test_usage_metadata_prefers_modality_breakdown():
    from models.llm.llm import GoogleLargeLanguageModel as LLM
    from google import genai

    details = [
        SimpleNamespace(modality=genai.types.MediaModality.TEXT, token_count=77),
    ]
    prompt, completion = LLM._calculate_tokens_from_usage_metadata(_usage(details, 999))
    assert prompt == 77
    assert completion == 10


def test_usage_metadata_falls_back_to_prompt_token_count():
    from models.llm.llm import GoogleLargeLanguageModel as LLM

    # No per-modality breakdown -> the API-level total must be used
    # (this is what avoids the expensive GPT-2 token-counting fallback).
    prompt, completion = LLM._calculate_tokens_from_usage_metadata(_usage(None, 123))
    assert prompt == 123
    assert completion == 10


def test_usage_metadata_all_missing_is_zero():
    from models.llm.llm import GoogleLargeLanguageModel as LLM

    assert LLM._calculate_tokens_from_usage_metadata(None) == (0, 0)
    # prompt missing everywhere -> 0 prompt tokens; completion still maps
    # thoughts + candidates (0 + 10 in the _usage default).
    assert LLM._calculate_tokens_from_usage_metadata(_usage(None, None)) == (
        0,
        10,
    )


# ---------------------------------------------------------------------------
# Embedding splitter: local GPT-2 counting (no API round-trip)
# ---------------------------------------------------------------------------


def _make_embedding_model() -> GeminiTextEmbeddingModel:
    return GeminiTextEmbeddingModel(model_schemas=[])


def test_splitter_never_calls_api_token_counting(monkeypatch):
    model = _make_embedding_model()
    monkeypatch.setattr(model, "_count_tokens", _boom)

    text = ("word " * 4000).strip()  # far above the context budget
    result = model._split_texts_to_fit_model_specs(
        client=None, model="m", texts=[text], context_size=256
    )

    assert len(result) >= 2
    for chunk, count in result:
        assert 0 < len(chunk) < len(text)
        assert count > 0


def test_splitter_short_text_passes_through():
    model = _make_embedding_model()
    result = model._split_texts_to_fit_model_specs(
        client=None, model="m", texts=["tiny"], context_size=8192
    )
    assert result == [("tiny", model._get_num_tokens_by_gpt2("tiny"))]


def test_splitter_cjk_dense_text_terminates(monkeypatch):
    """Token-dense (CJK) content where len(text) < context_size-as-tokens
    must still make progress and terminate (no infinite recursion)."""
    model = _make_embedding_model()
    monkeypatch.setattr(model, "_count_tokens", _boom)
    text = "字" * 300  # ~300 tokens by GPT-2, len() far below a real budget
    result = model._split_texts_to_fit_model_specs(
        client=None, model="m", texts=[text], context_size=8192
    )
    # Short relative to the budget: returned as-is (no split needed).
    total = sum(len(c) for c, _ in result)
    assert total == len(text)


def test_gpt2_counter_sanity():
    model = _make_embedding_model()
    n = model._get_num_tokens_by_gpt2("The quick brown fox jumps over the lazy dog.")
    assert 5 <= n <= 25

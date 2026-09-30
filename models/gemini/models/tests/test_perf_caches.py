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
from unittest.mock import Mock

import pytest

from dify_plugin.entities.model.message import UserPromptMessage

from models.llm import llm as gemini_llm
from models.llm.utils import FileCache
from models.text_embedding.text_embedding import (
    GeminiTextEmbeddingModel,
    _genai_emb_client_cache,
    _acquire_genai_client as _acquire_emb_client,
)


def _boom(*args, **kwargs):
    raise AssertionError("API token-counting round-trip attempted in splitter")


# ---------------------------------------------------------------------------
# LLM client cache
# ---------------------------------------------------------------------------


def test_llm_client_cache_returns_same_instance_for_same_creds():
    with gemini_llm._acquire_genai_client("key-a", None) as c1:
        with gemini_llm._acquire_genai_client("key-a", None) as c2:
            assert c1 is c2
    assert len(gemini_llm._genai_client_cache) == 1


def test_llm_client_cache_distinct_keys_distinct_clients():
    with gemini_llm._acquire_genai_client("key-a", None) as c1:
        with gemini_llm._acquire_genai_client("key-b", None) as c2:
            with gemini_llm._acquire_genai_client("key-a", "https://alt.example") as c3:
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

    with gemini_llm._acquire_genai_client("key-a", None) as client:
        with gemini_llm._acquire_genai_client("key-a", None) as again:
            assert client is again
    assert len(constructions) == 1
    assert constructions[0]["api_key"] == "key-a"


def test_llm_client_cache_lru_eviction_closes_oldest(monkeypatch):
    """When the bounded cache fills, the least-recently-used entry is evicted
    and its client is closed immediately (idle at eviction time)."""
    closed = []
    real_client_cls = gemini_llm.genai.Client

    class _CountingClient(real_client_cls):
        def close(self):
            closed.append(self)
            super().close()

    monkeypatch.setattr(gemini_llm.genai, "Client", _CountingClient)
    max_entries = gemini_llm._GENAI_CLIENT_CACHE_MAX

    for i in range(max_entries):
        with gemini_llm._acquire_genai_client(f"key-{i}", None):
            pass
    assert len(gemini_llm._genai_client_cache) == max_entries

    with gemini_llm._acquire_genai_client("overflow", None):
        pass
    assert len(gemini_llm._genai_client_cache) == max_entries
    assert len(closed) == 1
    # The evicted client is the LRU one (key-0) and it is the same instance the
    # cache used to hold for key-0.
    assert gemini_llm._genai_client_cache[("overflow", None)].client is not closed[0]


def test_llm_client_cache_lru_recently_used_survives(monkeypatch):
    closed = []
    real_client_cls = gemini_llm.genai.Client

    class _CountingClient(real_client_cls):
        def close(self):
            closed.append(self)
            super().close()

    monkeypatch.setattr(gemini_llm.genai, "Client", _CountingClient)
    max_entries = gemini_llm._GENAI_CLIENT_CACHE_MAX

    for i in range(max_entries):
        with gemini_llm._acquire_genai_client(f"key-{i}", None):
            pass
    # Touch key-0 so it is the most recently used, then overflow the cache.
    with gemini_llm._acquire_genai_client("key-0", None):
        pass
    with gemini_llm._acquire_genai_client("overflow", None):
        pass
    # key-1 (now the LRU) was evicted; key-0 survived.
    assert len(closed) == 1
    assert ("key-0", None) in gemini_llm._genai_client_cache
    assert ("key-1", None) not in gemini_llm._genai_client_cache


def test_llm_client_cache_evicted_busy_client_closed_after_release(monkeypatch):
    """An in-flight (leased) client that gets evicted must not be closed while
    the lease is held; it is closed by the releasing caller."""
    closed = []
    real_client_cls = gemini_llm.genai.Client

    class _CountingClient(real_client_cls):
        def close(self):
            closed.append(self)
            super().close()

    monkeypatch.setattr(gemini_llm.genai, "Client", _CountingClient)
    max_entries = gemini_llm._GENAI_CLIENT_CACHE_MAX

    with gemini_llm._acquire_genai_client("busy", None) as busy_client:
        for i in range(max_entries):
            with gemini_llm._acquire_genai_client(f"key-{i}", None):
                pass
        # busy is evicted (LRU) but its lease is still held -> not closed yet.
        assert ("busy", None) not in gemini_llm._genai_client_cache
        assert closed == []
    # Lease released -> the evicted busy client is closed.
    assert len(closed) == 1
    assert closed[0] is busy_client


def test_stream_lease_held_until_generator_exhausted(monkeypatch):
    """Regression: a stream generator (consumed after the invoking method has
    returned) must hold its client lease for its whole lifetime, so a cache
    churn during the stream cannot close the client."""
    closed = []
    real_client_cls = gemini_llm.genai.Client

    class _CountingClient(real_client_cls):
        def close(self):
            closed.append(self)
            super().close()

    monkeypatch.setattr(gemini_llm.genai, "Client", _CountingClient)

    def make_stream():
        with gemini_llm._acquire_genai_client("stream-key", None):
            yield "a"
            yield "b"

    gen = make_stream()
    assert next(gen) == "a"  # acquires the lease
    # Churn the cache while the stream generator is suspended mid-stream.
    for i in range(gemini_llm._GENAI_CLIENT_CACHE_MAX):
        with gemini_llm._acquire_genai_client(f"churn-{i}", None):
            pass
    # The stream client was evicted (LRU) but its lease is still held.
    assert closed == []
    assert next(gen) == "b"
    assert closed == []
    with pytest.raises(StopIteration):
        next(gen)
    # Exhaustion released the lease; the evicted client is now closed.
    assert len(closed) == 1


def test_generate_stream_lease_held_while_suspended(monkeypatch):
    """Method-level regression: ``_generate(stream=True)`` must hold the client
    lease for the whole stream iteration. If the method returned the stream
    generator after releasing the lease (the previous bug), a cache churn
    during the stream would close the client mid-stream."""
    closed = []

    class _FakeClient:
        instances = []

        def __init__(self, api_key=None, http_options=None):
            self.api_key = api_key
            self.closed = False
            self.models = Mock()
            self.models.generate_content_stream.return_value = iter(
                [SimpleNamespace(x=1)]
            )
            _FakeClient.instances.append(self)

        def close(self):
            self.closed = True
            closed.append(self)

    monkeypatch.setattr(gemini_llm.genai, "Client", _FakeClient)
    model = gemini_llm.GoogleLargeLanguageModel([])
    monkeypatch.setattr(
        model,
        "_handle_generate_stream_response",
        lambda *a, **k: iter([SimpleNamespace(x=1)]),
    )

    gen = model._generate(
        model="gemini-2.5-flash",
        credentials={"google_api_key": "k"},
        prompt_messages=[UserPromptMessage(content="hi")],
        model_parameters={},
        stream=True,
    )
    assert next(gen) is not None  # start the stream: acquire lease + first chunk
    stream_client = _FakeClient.instances[-1]

    # Churn the cache while the stream generator is suspended mid-stream.
    for i in range(gemini_llm._GENAI_CLIENT_CACHE_MAX):
        with gemini_llm._acquire_genai_client(f"churn-{i}", None):
            pass
    # The stream client was evicted (LRU) but its lease is still held.
    assert not stream_client.closed

    list(gen)  # exhaust: release the lease -> evicted client closed
    assert stream_client.closed


def test_llm_client_cache_concurrent_same_key_single_instance(monkeypatch):
    """Concurrent acquisitions of the same credential must all receive the same
    client instance and construct only one."""
    constructions = []
    real_client_cls = gemini_llm.genai.Client

    class _CountingClient(real_client_cls):
        def __init__(self, *args, **kwargs):
            constructions.append(kwargs)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(gemini_llm.genai, "Client", _CountingClient)
    results = []
    errors = []
    barrier = threading.Barrier(8)

    def worker():
        try:
            barrier.wait()
            with gemini_llm._acquire_genai_client("shared", None) as c:
                results.append(c)
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(constructions) == 1
    assert len({id(c) for c in results}) == 1


def test_llm_generate_sources_no_longer_build_raw_clients():
    """Regression guard: the hot paths must not construct genai.Client
    inline anymore (validate_credentials is the only allowed site).

    Note: this is a source-level guard scoped to the current layout; if the
    construction is refactored (e.g. through another helper), update it.
    """
    import inspect

    src = inspect.getsource(gemini_llm.GoogleLargeLanguageModel)
    raw_sites = src.count("genai.Client(")
    # _acquire_genai_client lives at module level, so inside the class body the
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
    with _acquire_emb_client("key-x") as c1:
        with _acquire_emb_client("key-x") as c2:
            with _acquire_emb_client("key-y") as c3:
                with _acquire_emb_client("key-x", "https://alt.example") as c4:
                    assert c1 is c2
                    assert c1 is not c3
                    assert c1 is not c4
    assert len(_genai_emb_client_cache) == 3


def test_emb_client_cache_is_separate_from_llm_cache():
    with gemini_llm._acquire_genai_client("same-key", None) as c:
        with _acquire_emb_client("same-key") as e:
            # Same credential, but the two modules keep independent instances.
            assert c is not e
    gemini_llm._genai_client_cache.clear()
    # Embedding cache survives the LLM cache being cleared (and vice versa).
    assert len(_genai_emb_client_cache) == 1


def test_emb_client_cache_evicts_and_closes(monkeypatch):
    closed = []
    real_client_cls = gemini_llm.genai.Client
    from models.text_embedding import text_embedding as emb_mod

    class _CountingClient(real_client_cls):
        def close(self):
            closed.append(self)
            super().close()

    monkeypatch.setattr(emb_mod.genai, "Client", _CountingClient)
    max_entries = emb_mod._GENAI_CLIENT_CACHE_MAX

    for i in range(max_entries):
        with _acquire_emb_client(f"key-{i}"):
            pass
    with _acquire_emb_client("overflow"):
        pass
    assert len(_genai_emb_client_cache) == max_entries
    assert len(closed) == 1


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


def test_splitter_fast_path_skips_api_token_counting(monkeypatch):
    """Text clearly below the near-limit ratio must use the local GPT-2
    estimate without any API round-trip."""
    model = _make_embedding_model()
    monkeypatch.setattr(model, "_count_tokens", _boom)

    text = ("word " * 100).strip()  # well below 0.8 * 256
    result = model._split_texts_to_fit_model_specs(
        client=None, model="m", texts=[text], context_size=256
    )

    assert result == [(text, model._get_num_tokens_by_gpt2(text))]


def test_splitter_short_text_passes_through():
    model = _make_embedding_model()
    result = model._split_texts_to_fit_model_specs(
        client=None, model="m", texts=["tiny"], context_size=8192
    )
    assert result == [("tiny", model._get_num_tokens_by_gpt2("tiny"))]


def test_splitter_boundary_at_ratio_uses_model_count(monkeypatch):
    """At exactly _NEAR_LIMIT_RATIO * context_size the model count is used
    (the fast path is strictly below the ratio)."""
    model = _make_embedding_model()
    monkeypatch.setattr(model, "_get_num_tokens_by_gpt2", lambda text: 256)
    calls = []
    monkeypatch.setattr(
        model, "_count_tokens", lambda client, model, text: calls.append(1) or 100
    )
    model._split_texts_to_fit_model_specs(
        client=None, model="m", texts=["x" * 50], context_size=320
    )
    assert calls == [1]


def test_splitter_near_limit_splits_with_model_count(monkeypatch):
    """Near the limit, the model-specific count is used to split; all text is
    preserved and every chunk reports a positive token count."""
    model = _make_embedding_model()
    monkeypatch.setattr(model, "_get_num_tokens_by_gpt2", lambda text: 300)
    monkeypatch.setattr(
        model, "_count_tokens", lambda client, model, text: 2 * len(text) or 1
    )
    text = "abc def ghi " * 50  # 500 chars; ~1000 tokens by the fake count
    result = model._split_texts_to_fit_model_specs(
        client=None, model="m", texts=[text], context_size=256
    )
    assert len(result) > 1
    total = sum(len(c) for c, _ in result)
    assert total == len(text)
    for chunk, count in result:
        assert 0 < count
        assert 0 < len(chunk) <= len(text)


def test_splitter_near_limit_accepts_when_model_count_below(monkeypatch):
    """Near the limit but with a model count below the budget: no split, and
    the verified count is returned."""
    model = _make_embedding_model()
    monkeypatch.setattr(model, "_get_num_tokens_by_gpt2", lambda text: 300)
    monkeypatch.setattr(model, "_count_tokens", lambda client, model, text: 150)
    text = "some near-limit text"
    result = model._split_texts_to_fit_model_specs(
        client=None, model="m", texts=[text], context_size=256
    )
    assert result == [(text, 150)]


def test_splitter_propagates_count_error_near_limit(monkeypatch):
    """A failing model count near the limit must propagate (fail closed) rather
    than fall back to the unverified GPT-2 estimate."""
    model = _make_embedding_model()
    monkeypatch.setattr(model, "_get_num_tokens_by_gpt2", lambda text: 300)

    def _raise(client, model, text):
        raise RuntimeError("count tokens unavailable")

    monkeypatch.setattr(model, "_count_tokens", _raise)
    with pytest.raises(RuntimeError, match="count tokens unavailable"):
        model._split_texts_to_fit_model_specs(
            client=None, model="m", texts=["x" * 50], context_size=256
        )


def test_splitter_cjk_dense_text_terminates_with_model_count(monkeypatch):
    """Token-dense (CJK) content where len(text) > context_size-as-tokens
    must still make progress and terminate (no infinite recursion), now with
    the model-count fallback active."""
    model = _make_embedding_model()
    # Deterministic model count: 1 token per character (dense, over budget).
    monkeypatch.setattr(model, "_count_tokens", lambda client, model, text: len(text))
    text = "字" * 300  # ~300 tokens by GPT-2, > context_size below
    result = model._split_texts_to_fit_model_specs(
        client=None, model="m", texts=[text], context_size=128
    )
    # Must actually split (token-dense) while preserving all characters.
    assert len(result) > 1
    total = sum(len(c) for c, _ in result)
    assert total == len(text)


def test_splitter_backward_snap_keeps_head_in_budget(monkeypatch):
    """Regression: a punctuation boundary found ahead of the cutoff must never
    push the head past the verified budget. The snap is backward-only, so a
    forward-only snap (the previous behavior) could accept an oversized head
    via the GPT-2 fast path when the local estimate undercounts."""
    model = _make_embedding_model()
    # GPT-2 estimate undercounts by 2x; the model count is exact (1 token/char).
    monkeypatch.setattr(
        model, "_get_num_tokens_by_gpt2", lambda text: max(1, len(text) // 2)
    )
    monkeypatch.setattr(model, "_count_tokens", lambda c, m, text: len(text))
    # 167 chars: initial estimate (83) is >= 0.8*100 so the model count runs;
    # cutoff lands near ~95, and the only "!" sits at ~150. A forward snap
    # would make the head ~151 chars (real 151 > 100) while its GPT-2 estimate
    # (75) would fast-path it; the backward snap keeps the head within budget.
    text = ("word " * 30) + "! tail" + "x" * 10
    result = model._split_texts_to_fit_model_specs(
        client=None, model="m", texts=[text], context_size=100
    )
    assert "".join(c for c, _ in result) == text
    for chunk, _ in result:
        # Real token count (1/char) of every emitted chunk fits the budget.
        assert len(chunk) <= 100


def test_emb_client_cache_busy_evicted_deferred_close(monkeypatch):
    """Mirror of the LLM busy-eviction test for the embedding cache."""
    closed = []
    real_client_cls = gemini_llm.genai.Client
    from models.text_embedding import text_embedding as emb_mod

    class _CountingClient(real_client_cls):
        def close(self):
            closed.append(self)
            super().close()

    monkeypatch.setattr(emb_mod.genai, "Client", _CountingClient)
    max_entries = emb_mod._GENAI_CLIENT_CACHE_MAX

    with _acquire_emb_client("busy") as busy_client:
        for i in range(max_entries):
            with _acquire_emb_client(f"key-{i}"):
                pass
        assert ("busy", None) not in _genai_emb_client_cache
        assert closed == []
    assert len(closed) == 1
    assert closed[0] is busy_client


def test_validate_credentials_closes_and_honors_base_url(monkeypatch):
    """validate_credentials must close its temporary client and forward
    google_base_url (it is outside the shared cache)."""
    created = []

    class _FakeClient:
        def __init__(self, api_key=None, http_options=None):
            self.api_key = api_key
            self.http_options = http_options
            self.models = Mock()
            self.closed = False
            created.append(self)

        def close(self):
            self.closed = True

    monkeypatch.setattr(gemini_llm.genai, "Client", _FakeClient)
    model = gemini_llm.GoogleLargeLanguageModel([])
    model.validate_credentials(
        "gemini-2.5-flash",
        {"google_api_key": "k", "google_base_url": "https://alt.example"},
    )
    assert len(created) == 1
    assert created[0].closed
    assert created[0].http_options.base_url == "https://alt.example"


def test_emb_validate_credentials_closes_and_honors_base_url(monkeypatch):
    created = []

    class _FakeClient:
        def __init__(self, api_key=None, http_options=None):
            self.api_key = api_key
            self.http_options = http_options
            self.models = Mock()
            self.closed = False
            created.append(self)

        def close(self):
            self.closed = True

    from models.text_embedding import text_embedding as emb_mod

    monkeypatch.setattr(emb_mod.genai, "Client", _FakeClient)
    model = _make_embedding_model()
    model.validate_credentials(
        "gemini-embedding-001",
        {"google_api_key": "k", "google_base_url": "https://alt.example"},
    )
    assert len(created) == 1
    assert created[0].closed
    assert created[0].http_options.base_url == "https://alt.example"


def test_gpt2_counter_sanity():
    model = _make_embedding_model()
    n = model._get_num_tokens_by_gpt2("The quick brown fox jumps over the lazy dog.")
    assert 5 <= n <= 25

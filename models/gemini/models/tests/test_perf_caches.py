"""Offline unit tests for the gemini plugin's in-memory FileCache.

Covers, without any network access or API key:

- thread-safe in-memory FileCache (concurrency, expiry, eviction)
- backward-compatible constructor signature

These tests are intentionally NOT marked ``live`` so they run in CI without
a GEMINI_API_KEY.
"""

import threading
import time

from models.llm.utils import FileCache


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


def test_filecache_hard_cap_bounds_live_entries():
    cache = FileCache()
    cap = cache._MAX_LIVE_ENTRIES
    for i in range(cap + 25):
        cache.setex(f"k{i}", 3600, f"v{i}")

    # The cache never exceeds the hard cap, and the oldest entries (insertion
    # order) were the ones dropped.
    assert len(cache._cache) == cap
    assert not cache.exists("k0")
    assert not cache.exists("k24")
    assert cache.exists(f"k{cap + 24}")
    assert cache.get(f"k{cap + 24}") == f"v{cap + 24}"

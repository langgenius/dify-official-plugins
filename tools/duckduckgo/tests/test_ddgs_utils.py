"""In-process tests for tools/ddgs_utils.py (pytest-shaped).

No network: ``DDGS`` is replaced with a fake client, and ``time``/``random`` inside the
module under test are replaced with a frozen clock and a zero jitter source so that both
the backoff delays and the throttle slots are exact numbers.

The concurrency cases mirror the workflow this fix came from: several DuckDuckGo search
nodes fanned out in parallel inside a loop, which is what bursts the upstream engines.
"""

from __future__ import annotations

import sys
import threading
import types
from pathlib import Path
from typing import Any

import pytest

_HERE = Path(__file__).resolve().parent
_PLUGIN_ROOT = _HERE.parent
sys.path.insert(0, str(_PLUGIN_ROOT))


def _ensure_stub_ddgs() -> None:
    """Allow importing the helper without the real ``ddgs`` package installed.

    CI installs the plugin's dependencies, so the real package is normally used; the tests
    never touch it either way because ``DDGS`` is patched out.
    """
    if "ddgs" in sys.modules:
        return
    try:
        import ddgs  # noqa: F401

        return
    except ImportError:
        pass

    exceptions_stub = types.ModuleType("ddgs.exceptions")
    exceptions_stub.DDGSException = type("DDGSException", (Exception,), {})
    ddgs_stub = types.ModuleType("ddgs")
    ddgs_stub.DDGS = type("DDGS", (), {})
    ddgs_stub.exceptions = exceptions_stub
    sys.modules["ddgs"] = ddgs_stub
    sys.modules["ddgs.exceptions"] = exceptions_stub


_ensure_stub_ddgs()

from ddgs.exceptions import DDGSException

from tools import ddgs_utils

TEXT_RESULTS = [{"title": "t", "href": "https://example.com", "body": "b"}]
IMAGE_RESULTS = [{"title": "i", "image": "https://example.com/i.png"}]


class FrozenClock:
    """``time`` replacement that never advances but records every requested sleep.

    Freezing ``monotonic`` makes the slot arithmetic in ``_wait_for_slot`` deterministic no
    matter how the threads interleave: with ``now`` pinned at 0, the Nth caller to take the
    lock is always handed slot ``N * MIN_INTERVAL_SECONDS``.
    """

    def __init__(self) -> None:
        self.sleeps: list[float] = []
        self._lock = threading.Lock()

    def monotonic(self) -> float:
        return 0.0

    def sleep(self, seconds: float) -> None:
        with self._lock:
            self.sleeps.append(seconds)


class FakeClientFactory:
    """Stands in for the ``DDGS`` class, one instance per attempt.

    ``outcomes`` is consumed one entry per search call: an exception instance is raised, a
    list is returned. The last entry repeats once the list is exhausted.
    """

    def __init__(self, outcomes: list[Any]) -> None:
        self._outcomes = outcomes
        self.constructions: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def __call__(self, proxy: str | None = None, timeout: int | None = None):
        with self._lock:
            self.constructions.append({"proxy": proxy, "timeout": timeout})
        return _FakeClient(self)

    def _run(self, category: str, query: str, kwargs: dict[str, Any]) -> list[dict]:
        with self._lock:
            index = len(self.calls)
            self.calls.append({"category": category, "query": query, "kwargs": kwargs})
        outcome = self._outcomes[min(index, len(self._outcomes) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _FakeClient:
    def __init__(self, factory: FakeClientFactory) -> None:
        self._factory = factory

    def text(self, query: str, **kwargs: Any) -> list[dict]:
        return self._factory._run("text", query, kwargs)

    def images(self, query: str, **kwargs: Any) -> list[dict]:
        return self._factory._run("images", query, kwargs)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> FrozenClock:
    """Freeze the clock, zero the jitter, and reset the module-level throttle state."""
    frozen = FrozenClock()
    monkeypatch.setattr(ddgs_utils, "time", frozen)
    monkeypatch.setattr(ddgs_utils, "random", types.SimpleNamespace(uniform=lambda _a, _b: 0.0))
    monkeypatch.setattr(ddgs_utils, "_next_slot_at", 0.0)
    return frozen


@pytest.fixture
def no_throttle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop the throttle so a test sees only the retry backoff sleeps."""
    monkeypatch.setattr(ddgs_utils, "_wait_for_slot", lambda: None)


def _install_client(monkeypatch: pytest.MonkeyPatch, outcomes: list[Any]) -> FakeClientFactory:
    factory = FakeClientFactory(outcomes)
    monkeypatch.setattr(ddgs_utils, "DDGS", factory)
    return factory


def test_success_on_first_attempt_builds_one_client(clock, no_throttle, monkeypatch):
    factory = _install_client(monkeypatch, [TEXT_RESULTS])

    results = ddgs_utils.search_with_retry("text", "dify", max_results=5)

    assert results == TEXT_RESULTS
    assert len(factory.constructions) == 1
    assert factory.calls == [{"category": "text", "query": "dify", "kwargs": {"max_results": 5}}]
    assert clock.sleeps == []


def test_image_category_is_dispatched_by_name(clock, no_throttle, monkeypatch):
    factory = _install_client(monkeypatch, [IMAGE_RESULTS])

    results = ddgs_utils.search_with_retry("images", "cats", timelimit="Day")

    assert results == IMAGE_RESULTS
    assert factory.calls[0]["category"] == "images"
    assert factory.calls[0]["kwargs"] == {"timelimit": "Day"}


def test_transient_failure_then_success_retries_with_a_fresh_client(
    clock, no_throttle, monkeypatch
):
    factory = _install_client(
        monkeypatch, [DDGSException(ddgs_utils.DDGS_NO_RESULTS_MESSAGE), TEXT_RESULTS]
    )

    results = ddgs_utils.search_with_retry("text", "dify")

    assert results == TEXT_RESULTS
    # A new DDGS instance per attempt is the point: it re-randomises the browser
    # fingerprint and the engine order, which is what makes the retry worth doing.
    assert len(factory.constructions) == 2
    assert clock.sleeps == [ddgs_utils.BASE_RETRY_DELAY_SECONDS]


def test_attempt_exhaustion_uses_exponential_backoff(clock, no_throttle, monkeypatch):
    factory = _install_client(
        monkeypatch, [DDGSException("boom"), DDGSException("boom"), DDGSException("boom")]
    )

    with pytest.raises(DDGSException):
        ddgs_utils.search_with_retry("text", "dify")

    assert len(factory.constructions) == ddgs_utils.MAX_ATTEMPTS
    # Backoff between attempts only, never after the final one.
    assert clock.sleeps == [2.0, 4.0]


def test_exhausted_no_results_error_explains_the_likely_block(clock, no_throttle, monkeypatch):
    last = DDGSException(ddgs_utils.DDGS_NO_RESULTS_MESSAGE)
    _install_client(monkeypatch, [DDGSException(ddgs_utils.DDGS_NO_RESULTS_MESSAGE), last])
    monkeypatch.setattr(ddgs_utils, "MAX_ATTEMPTS", 2)

    with pytest.raises(DDGSException) as excinfo:
        ddgs_utils.search_with_retry("text", "dify")

    message = str(excinfo.value)
    assert "'dify'" in message
    assert "2 attempts" in message
    # The helper cannot tell a block from a genuinely empty result set, so the message has
    # to name the likely cause without asserting it, and point at the workarounds.
    assert "usually" in message
    assert "no matches" in message
    assert "proxy_server" in message
    assert "backend" in message
    assert excinfo.value.__cause__ is last


def test_other_errors_keep_the_upstream_text(clock, no_throttle, monkeypatch):
    _install_client(monkeypatch, [DDGSException("proxy refused the connection")])
    monkeypatch.setattr(ddgs_utils, "MAX_ATTEMPTS", 1)

    with pytest.raises(DDGSException) as excinfo:
        ddgs_utils.search_with_retry("text", "dify")

    message = str(excinfo.value)
    assert "proxy refused the connection" in message
    assert "usually" not in message


def test_proxy_and_timeout_reach_the_client(clock, no_throttle, monkeypatch):
    factory = _install_client(monkeypatch, [TEXT_RESULTS])

    ddgs_utils.search_with_retry("text", "dify", proxy="http://127.0.0.1:8080")

    assert factory.constructions[0] == {
        "proxy": "http://127.0.0.1:8080",
        "timeout": ddgs_utils.REQUEST_TIMEOUT_SECONDS,
    }


def test_backend_is_forwarded_as_a_search_argument(clock, no_throttle, monkeypatch):
    factory = _install_client(monkeypatch, [TEXT_RESULTS])

    ddgs_utils.search_with_retry("text", "dify", backend=" duckduckgo,brave ", max_results=3)

    assert factory.calls[0]["kwargs"] == {"backend": "duckduckgo,brave", "max_results": 3}


@pytest.mark.parametrize("backend", [None, "", "   "])
def test_blank_backend_leaves_ddgs_rotation_alone(clock, no_throttle, monkeypatch, backend):
    factory = _install_client(monkeypatch, [TEXT_RESULTS])

    ddgs_utils.search_with_retry("text", "dify", backend=backend)

    assert "backend" not in factory.calls[0]["kwargs"]


def test_empty_query_is_rejected_before_any_request(clock, no_throttle, monkeypatch):
    factory = _install_client(monkeypatch, [TEXT_RESULTS])

    with pytest.raises(ValueError):
        ddgs_utils.search_with_retry("text", "")

    assert factory.constructions == []


def _run_concurrently(count: int, query_prefix: str = "q") -> None:
    errors: list[Exception] = []

    def worker(index: int) -> None:
        try:
            ddgs_utils.search_with_retry("text", f"{query_prefix}{index}")
        except Exception as exc:  # noqa: BLE001 - re-raised by the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not any(thread.is_alive() for thread in threads), "throttle deadlocked"
    assert not errors, errors


def test_parallel_searches_are_spaced_one_slot_apart(clock, monkeypatch):
    """Five parallel search nodes, the shape that triggered the rate limiting."""
    _install_client(monkeypatch, [TEXT_RESULTS])

    _run_concurrently(5)

    # First caller starts immediately (no sleep), the rest queue up behind it.
    assert sorted(clock.sleeps) == [2.0, 4.0, 6.0, 8.0]
    assert ddgs_utils._next_slot_at == 5 * ddgs_utils.MIN_INTERVAL_SECONDS


def test_looping_over_parallel_searches_keeps_slots_monotonic(clock, monkeypatch):
    """Three loop iterations of five parallel nodes never reuse a slot."""
    _install_client(monkeypatch, [TEXT_RESULTS])

    for round_index in range(3):
        _run_concurrently(5, query_prefix=f"r{round_index}q")

    assert sorted(clock.sleeps) == [2.0 * i for i in range(1, 15)]
    assert ddgs_utils._next_slot_at == 15 * ddgs_utils.MIN_INTERVAL_SECONDS


def test_without_the_throttle_the_same_calls_would_burst(clock, no_throttle, monkeypatch):
    """Control for the two tests above: unthrottled, all five start at once."""
    _install_client(monkeypatch, [TEXT_RESULTS])

    _run_concurrently(5)

    assert clock.sleeps == []

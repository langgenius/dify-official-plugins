import logging
import os
import random
import threading
import time
from typing import Any

from ddgs import DDGS
from ddgs.exceptions import DDGSException


class SearchUnavailable(DDGSException):
    """Every attempt of a search ended without results.

    ``user_text`` is the plain-language report meant for the workflow user (what each engine
    said, how long we tried, and that this is the engines' treatment of this server rather than a
    fault in the query or the tool); ``report`` is the same as a dict. ``str(exc)`` carries the
    full detail for the backend log.
    """

    user_text: str = ""
    report: dict[str, Any] = {}

from tools import ddgs_hardening

logger = logging.getLogger(__name__)

# Pin a desktop fingerprint, add the Yahoo mobile-layout parser, record per-engine
# diagnostics, re-send dropped connections. Measurements and switches: tools/ddgs_hardening.py.
ddgs_hardening.apply()

# Attempts per search. A retry only helps a transient fault (a dropped
# connection, a slow engine), and those succeed on the next attempt; a search that every engine
# refuses does not recover by asking again. 3 leaves headroom beyond that while keeping a search
# no engine can answer inside the time a caller is prepared to wait for one node.
MAX_ATTEMPTS = 3
# Exponential backoff between attempts: 2s, 4s (each plus up to 1s of jitter).
BASE_RETRY_DELAY_SECONDS = 2.0
RETRY_JITTER_SECONDS = 1.0
# Minimum gap between two searches started by this plugin process. Workflows commonly fan
# several search nodes out in parallel and loop over them; without a gap they all hit the
# engines at once and the whole host gets rate-limited.
MIN_INTERVAL_SECONDS = 1.0
# ddgs defaults to 5s, which is short enough that slower engines (brave, mojeek, startpage)
# are abandoned before they answer, leaving only the engines most likely to be blocked.
REQUEST_TIMEOUT_SECONDS = 10

# The exact message ddgs raises when every backend returned nothing without raising.
DDGS_NO_RESULTS_MESSAGE = "No results found."

# The Dify plugin SDK gevent-monkey-patches the plugin process (dify_plugin/_gevent.py), so the
# SDK's "thread pool" of tool invocations is really greenlets on one OS thread. ddgs/primp do
# their HTTP in Rust and block that thread, which serialises every search engine request in the
# whole plugin. Run the blocking
# ddgs call on gevent's native thread pool instead, so concurrent tool invocations overlap.
# DDG_BLOCKING_THREADS = pool size (0 = off, call inline).
BLOCKING_THREADS = int(os.environ.get("DDG_BLOCKING_THREADS", "16"))


def _gevent_patched() -> bool:
    try:
        from gevent import monkey
    except ImportError:
        return False
    return bool(monkey.is_module_patched("threading"))


def _run_blocking(fn, *args, **kwargs):
    """Call fn(*args, **kwargs); on a real OS thread if this process is gevent-patched."""
    if BLOCKING_THREADS <= 0 or not _gevent_patched():
        return fn(*args, **kwargs)
    import gevent

    pool = gevent.get_hub().threadpool
    if pool.maxsize < BLOCKING_THREADS:
        pool.maxsize = BLOCKING_THREADS
    return pool.apply(fn, args, kwargs)

_throttle_lock = threading.Lock()
_next_slot_at = 0.0


def _wait_for_slot() -> None:
    """Block until this caller may start a search, spacing callers MIN_INTERVAL_SECONDS apart."""
    global _next_slot_at
    with _throttle_lock:
        now = time.monotonic()
        slot = max(now, _next_slot_at)
        _next_slot_at = slot + MIN_INTERVAL_SECONDS
    delay = slot - now
    if delay > 0:
        logger.debug("ddgs throttle: waiting %.1fs for next search slot", delay)
        time.sleep(delay)


def candidate_engines(category: str, backend: str | None) -> list[str] | None:
    """Public alias of the engine list a search may ask (see ``_candidate_engines``)."""
    return _candidate_engines(category, backend)


def _candidate_engines(category: str, backend: str | None) -> list[str] | None:
    """Engines a search may ask: the node's pinned list, else ddgs' rotation (None if unknown)."""
    if backend and backend.strip():
        return [e.strip() for e in backend.split(",") if e.strip()]
    return ddgs_hardening.rotation(category)


def _retry_delay(attempt: int) -> float:
    delay = BASE_RETRY_DELAY_SECONDS * (2 ** (attempt - 1))
    return delay + random.uniform(0, RETRY_JITTER_SECONDS)


def search_with_retry(
    category: str,
    query: str,
    proxy: str | None = None,
    backend: str | None = None,
    **kwargs: Any,
) -> list[dict]:
    """Run a ddgs search (``text``, ``images`` ...) with throttling and retry on failure.

    ddgs raises ``DDGSException("No results found.")`` whenever every backend returned nothing
    *without* raising. That is far more often a block than an empty result set:
    ``BaseSearchEngine.request`` maps any non-200 (403, 429, captcha redirect) to ``None``, and a
    200 captcha page parses to zero results, so the status code is discarded before it can reach
    the caller. Even nonsense queries return results from at least one of the real engines.

    Each ``DDGS()`` instance picks a fresh random browser fingerprint (primp ``impersonate="random"``)
    and reshuffles the engine order, so retrying with a new instance has a real chance of reaching an
    engine that answers. Attempts are spaced with exponential backoff, and all searches from this
    process are throttled to MIN_INTERVAL_SECONDS apart so parallel workflow nodes do not burst.

    ``backend`` is a comma-separated list of ddgs engine names (e.g. ``"duckduckgo,brave,yahoo"``).
    Leave it empty for ddgs' ``auto`` rotation. Unknown names are logged by ddgs and skipped.
    If every attempt fails, re-raise with a message that says what actually happened instead of
    the misleading upstream text.
    """
    if not query:
        raise ValueError("query is required")

    if backend and backend.strip():
        kwargs["backend"] = backend.strip()

    last_error: DDGSException | None = None
    search_started = time.monotonic()
    ddgs_hardening.clear_diagnostics(query)
    attempt_history: list[str] = []
    # Engines that served a proper page (with or without hits) are not asked again: they return
    # the same page on every ask. Each retry goes only to the engines that refused, timed out or
    # dropped, and the search ends as soon as no such engine is left.
    candidates = _candidate_engines(category, kwargs.get("backend"))
    attempts_made = 0
    for attempt in range(1, MAX_ATTEMPTS + 1):
        attempts_made = attempt
        _wait_for_slot()
        attempt_started = time.monotonic()
        try:
            client = DDGS(proxy=proxy, timeout=REQUEST_TIMEOUT_SECONDS)
            if ddgs_hardening.fanout_active():
                # the fan-out already runs each engine on a real thread; stay on this greenlet
                results = getattr(client, category)(query, **kwargs)
            else:
                results = _run_blocking(getattr(client, category), query, **kwargs)
            rows = ddgs_hardening.diagnostics_for(query, since=attempt_started)
            logger.info(
                "ddgs %s search ok for %r on attempt %d/%d: %d results, supplied by %s [engines: %s]",
                category,
                query,
                attempt,
                MAX_ATTEMPTS,
                len(results),
                ddgs_hardening.suppliers(rows),
                ddgs_hardening.summarize(rows),
            )
            return results
        except DDGSException as ex:
            last_error = ex
            engines_seen = ddgs_hardening.summarize(
                ddgs_hardening.diagnostics_for(query, since=attempt_started)
            )
            attempt_history.append(f"attempt {attempt}: {engines_seen}")
            logger.warning(
                "ddgs %s search attempt %d/%d failed for %r: %r [engines: %s]",
                category,
                attempt,
                MAX_ATTEMPTS,
                query,
                ex,
                engines_seen,
            )
            if attempt < MAX_ATTEMPTS:
                time.sleep(_retry_delay(attempt))
            # Decide after the wait, over everything recorded for this query, so an engine whose
            # page arrived just after the attempt's deadline counts as answered too.
            answered = ddgs_hardening.answered_engines(ddgs_hardening.diagnostics_for(query))
            if candidates is not None:
                remaining = [e for e in candidates if e not in answered]
                if not remaining:
                    logger.info(
                        "ddgs %s search for %r: every engine answered with no results; not retrying",
                        category,
                        query,
                    )
                    break
                kwargs["backend"] = ",".join(remaining)

    # The report a workflow user sees (user_text); the log line adds the per-engine detail.
    rows = ddgs_hardening.diagnostics_for(query)
    headline, detail = ddgs_hardening.verdict(rows)
    seconds = time.monotonic() - search_started
    required = kwargs.get("max_results")
    pinned = (backend or "").strip()
    closing = (
        "The search engines may be limiting requests, or the selected engine(s) have no result for this "
        "query. Please try a different query, enable more engines, or try again later. If the issue "
        "persists, contact your Dify administrator with this message."
    )
    if pinned:
        closing = f"This search was limited to the engines: {pinned}. " + closing
    if str(last_error) != DDGS_NO_RESULTS_MESSAGE:
        closing += f" Last error: {last_error}."
    user_text = "\n".join(
        [
            f"Search did not return results for query: {query}",
            "Results received: 0",
            "",
            closing,
        ]
    )
    message = (
        f"SEARCH FAILED: {user_text}\n"
        f"Attempts: {attempts_made} over {seconds:.0f} s. Verdict: {headline}. Engines (last attempt): {'; '.join(ddgs_hardening.engine_lines(rows))}. "
        "Operator options: set proxy_server, or pin the Search engines field to engines that still answer."
    )
    if attempt_history:
        message += " Raw engine responses per attempt: " + " | ".join(attempt_history) + "."
    logger.warning("ddgs %s search gave up for %r: %s", category, query, message)
    exc = SearchUnavailable(message)
    exc.user_text = user_text
    exc.report = {
        "query": query,
        "reason": headline,
        "engines": detail,
        "attempts": attempts_made,
        "seconds": round(seconds),
        "results_received": 0,
        "results_required": required,
        "pinned_engines": pinned or None,
        "raw_attempts": list(attempt_history),
    }
    raise exc from last_error

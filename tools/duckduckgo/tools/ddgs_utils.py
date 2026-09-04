import logging
import random
import threading
import time
from typing import Any

from ddgs import DDGS
from ddgs.exceptions import DDGSException

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
# Exponential backoff between attempts: 2s, 4s (each plus up to 1s of jitter).
BASE_RETRY_DELAY_SECONDS = 2.0
RETRY_JITTER_SECONDS = 1.0
# Minimum gap between two searches started by this plugin process. Workflows commonly fan
# several search nodes out in parallel and loop over them; without a gap they all hit the
# engines at once and the whole host gets rate-limited.
MIN_INTERVAL_SECONDS = 2.0
# ddgs defaults to 5s, which is short enough that slower engines (brave, mojeek, startpage)
# are abandoned before they answer, leaving only the engines most likely to be blocked.
REQUEST_TIMEOUT_SECONDS = 10

# The exact message ddgs raises when every backend returned nothing without raising.
DDGS_NO_RESULTS_MESSAGE = "No results found."

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


def _retry_delay(attempt: int) -> float:
    return BASE_RETRY_DELAY_SECONDS * (2 ** (attempt - 1)) + random.uniform(0, RETRY_JITTER_SECONDS)


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
    for attempt in range(1, MAX_ATTEMPTS + 1):
        _wait_for_slot()
        try:
            client = DDGS(proxy=proxy, timeout=REQUEST_TIMEOUT_SECONDS)
            return getattr(client, category)(query, **kwargs)
        except DDGSException as ex:
            last_error = ex
            logger.warning(
                "ddgs %s search attempt %d/%d failed for %r: %r",
                category,
                attempt,
                MAX_ATTEMPTS,
                query,
                ex,
            )
            if attempt < MAX_ATTEMPTS:
                time.sleep(_retry_delay(attempt))

    if str(last_error) == DDGS_NO_RESULTS_MESSAGE:
        message = (
            f"DuckDuckGo {category} search returned nothing for {query!r} after {MAX_ATTEMPTS} attempts. "
            "ddgs reports 'No results found.' when every upstream search engine answered with a "
            "non-200 status or a captcha page, so this almost always means the engines blocked this "
            "server's requests rather than that the query has no matches. Retry later, reduce how "
            "many searches the workflow runs at once, set proxy_server, or pin backend to engines "
            "that still answer from this host."
        )
    else:
        message = f"DuckDuckGo {category} search failed after {MAX_ATTEMPTS} attempts: {last_error}"
    raise DDGSException(message) from last_error

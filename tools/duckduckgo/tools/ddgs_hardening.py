"""Hardening for ddgs scraping inside this plugin (applied once at import by ddgs_utils).

Brave/Google/Mojeek/Startpage/DuckDuckGo were blocked
(429/403/202/captcha) and Yahoo was the only engine answering: most "No results found."
failures were NOT empty results. ddgs sends a *random* browser+OS fingerprint per request;
with a mobile (iOS/Android) fingerprint Yahoo serves a mobile page layout that the ddgs Yahoo
parser cannot read, and with mobile/non-browser fingerprints it sometimes serves a
"We had temporary problems searching for web pages" page.

Five independent measures, each switchable by env var (all default ON):

1. DDG_DESKTOP_FINGERPRINT      pin impersonate_os to windows/macos (browser still random).
2. DDG_YAHOO_MOBILE_PARSER      fallback parser for Yahoo's mobile layout, in case a mobile
                                page still arrives.
3. DDG_ENGINE_DIAGNOSTICS       record, per engine call, the HTTP status and a page
                                classification (rate-limit / captcha / throttle page /
                                unparsed layout / ok). Surfaced in the error message when a
                                search finally fails, and in WARNING logs per failed attempt.
4. DDG_TRANSPORT_RETRIES        re-send a request whose connection was dropped by the engine
                                ("peer closed connection without sending TLS close_notify",
                                seen from Yahoo under concurrency) after a short pause, instead
                                of failing the whole attempt (0 = off).
5. DDG_GOOGLE_CURL_CFFI         send the Google engine's request through curl_cffi with an
                                old-Chrome profile (DDG_GOOGLE_IMPERSONATE, default
                                chrome99_android) and no cookies, instead of primp. Google's
                                /wml/search endpoint answers that pairing and refuses every
                                primp profile (primp only ships current browser versions) as well as
                                any request carrying the CONSENT cookie ddgs sets. Falls back
                                to primp if curl_cffi is missing.
"""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


def _route_plugin_logs_to_daemon() -> None:
    """Send this package's log lines through the Dify plugin SDK's handler.

    The SDK attaches its stdout JSON handler only to its own ``dify_plugin`` logger; loggers under
    ``tools.*`` have no handler, so their INFO/WARNING lines (which engine supplied results, which
    refused) never reached the plugin-daemon log. Attach the same handler to the ``tools`` logger.
    """
    import sys

    if "dify_plugin" not in sys.modules:
        # Only inside a real plugin process (main.py imports dify_plugin first). Importing the SDK
        # here would gevent-monkey-patch whatever imported us (tests, local harnesses).
        return
    try:
        from dify_plugin.config.logger_format import plugin_logger_handler
    except Exception:  # pragma: no cover
        return
    pkg_logger = logging.getLogger("tools")
    if plugin_logger_handler not in pkg_logger.handlers:
        pkg_logger.addHandler(plugin_logger_handler)
    pkg_logger.setLevel(logging.INFO)


_route_plugin_logs_to_daemon()


# --- settings -------------------------------------------------------------------------
def _flag(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() not in ("0", "false", "no", "off", "")


DESKTOP_FINGERPRINT = _flag("DDG_DESKTOP_FINGERPRINT")
DESKTOP_OS_CHOICES = ("windows", "macos")  # the desktop profiles Yahoo serves its parseable layout to
YAHOO_MOBILE_PARSER = _flag("DDG_YAHOO_MOBILE_PARSER")
ENGINE_DIAGNOSTICS = _flag("DDG_ENGINE_DIAGNOSTICS")
# 4. Transport-level retry: Yahoo drops HTTP/2 connections under concurrency ("peer closed
#    connection without sending TLS close_notify"). ddgs turns that into a DDGSException
#    for the whole engine call, which costs a full attempt + backoff. Re-send the same
#    request up to this many extra times after a short pause instead (0 = off).
TRANSPORT_RETRIES = int(os.environ.get("DDG_TRANSPORT_RETRIES", "2"))
TRANSPORT_RETRY_DELAY_SECONDS = 0.5
TRANSPORT_ERROR_MARKERS = (
    "close_notify",
    "error sending request",
    "connection reset",
    "connection closed",
    "unexpected eof",
    "broken pipe",
    "connectionerror",
    "requesterror",
)

# 5. Google through curl_cffi. Google's endpoint answers an old-Chrome/Edge TLS+header profile
#    (curl_cffi chrome99/chrome101/edge101) sent with no cookies -> results page; the same
#    request with CONSENT=YES+ (which ddgs sets), or over HTTP/1.1, or without the impersonated
#    browser's default headers, or with any current Chrome/Firefox/Safari profile (all primp offers)
#    -> Google's /sorry/ interstitial (429).
GOOGLE_CURL_CFFI = _flag("DDG_GOOGLE_CURL_CFFI")
GOOGLE_IMPERSONATE = os.environ.get("DDG_GOOGLE_IMPERSONATE", "chrome99_android").strip() or "chrome99_android"
GOOGLE_ENGINES = ("google",)

# 6. Engine fan-out. ddgs asks the engines in rounds of ceil(max_results/10)+1 (two for the node
#    default of 5), waits for the whole round and only then starts the next, so every dead engine
#    ahead of a live one delays the search and a non-answering engine costs the full request
#    timeout. Ask every engine at once on real OS threads and return as soon as the pooled,
#    de-duplicated results reach max_results. Engines still in flight finish on their own.
ENGINE_FANOUT = _flag("DDG_ENGINE_FANOUT")
FANOUT_THREADS = int(os.environ.get("DDG_FANOUT_THREADS", "64"))
FANOUT_POLL_SECONDS = 0.05

# 7. Engines no HTTP client can pass. Startpage serves a JavaScript proof-of-work challenge to
#    every client without a browser engine, from every address; asking it only wastes a request
#    per search. Removed from the ddgs registry, the same way upstream disables Bing and Yandex:
#    neither 'auto' nor the node's Search engines field can reach a removed engine (a name typed
#    there falls back to 'auto'). Comma-separated; empty string keeps every engine.
DISABLED_ENGINES = tuple(
    e.strip().lower() for e in os.environ.get("DDG_DISABLED_ENGINES", "startpage").split(",") if e.strip()
)

# labels that mean "this page/status was a refusal" (used only for diagnostics)
BLOCK_KINDS = {"429-ratelimit", "403-forbidden", "202-ratelimit", "captcha-page", "throttle-page"}

# Deliberately NO per-engine cooldown / backend narrowing here. An earlier build skipped engines
# that had just refused; under a burst every web engine refuses within a minute, the backend
# list collapsed to wikipedia+grokipedia (which cannot answer ordinary web queries) and every
# search failed. ddgs 'auto' re-asks a blocked engine in milliseconds, so there is nothing to save.


def is_transport_error(ex: BaseException) -> bool:
    """True for connection-level failures worth re-sending (not timeouts, not HTTP statuses)."""
    if type(ex).__name__ == "TimeoutException":
        return False
    text = f"{type(ex).__name__}: {ex} {type(ex.__cause__).__name__ if ex.__cause__ else ''}".lower()
    return any(m in text for m in TRANSPORT_ERROR_MARKERS)

# --- per-thread diagnostics -----------------------------------------------------------
_local = threading.local()  # engine worker threads: current engine/query
_diag_lock = threading.Lock()
_diag: dict[str, list[tuple[float, str, Any, int, str]]] = {}  # query -> [(ts, engine, status, bytes, kind)]


def classify(engine: str, status: Any, body: str) -> str:
    """Turn a raw engine response into a short label."""
    b = (body or "").lower()
    if status == 429:
        return "429-ratelimit"
    if status == 403:
        return "403-forbidden"
    if status == 202 and engine.startswith("duckduckgo"):
        return "202-ratelimit"
    if status != 200:
        return f"{status}"
    if "temporary problems searching" in b:
        return "throttle-page"
    if any(m in b for m in ("captcha", "unusual traffic", "verify you are human")):
        return "captcha-page"
    if '"challenge":{' in b and '"difficulty"' in b:
        # JavaScript proof-of-work gate (seen from Startpage as a 22 kB HTTP 200 with no results)
        return "captcha-page"
    if engine == "yahoo":
        if "relsrch" in b:
            return "ok-desktop"
        if "grp-talgo" in b or "algo-sr" in b:
            return "ok-mobile-layout"
        return "empty"
    if len(b) < 200:
        return "empty"
    return "ok"


def _record(query: str | None, engine: str, status: Any, size: int, kind: str) -> None:
    now = time.monotonic()
    with _diag_lock:
        if query is not None:
            _diag.setdefault(query, []).append((now, engine, status, size, kind))
            if len(_diag) > 200:  # keep memory bounded
                for k in list(_diag)[:100]:
                    _diag.pop(k, None)


def _relabel_blocks_as_ok(query: str | None, engine: str) -> None:
    """The engine parsed results from its last page: downgrade a block label on that page to 'ok'."""
    if query is None:
        return
    with _diag_lock:
        rows = _diag.get(query, [])
        for i in range(len(rows) - 1, -1, -1):
            ts, e, st, size, kind = rows[i]
            if e == engine:
                if kind in BLOCK_KINDS:
                    rows[i] = (ts, e, st, size, f"ok(words:{kind})")
                break


def diagnostics_for(query: str, since: float | None = None) -> list[tuple[float, str, Any, int, str]]:
    with _diag_lock:
        rows = list(_diag.get(query, []))
    return [r for r in rows if since is None or r[0] >= since]


def clear_diagnostics(query: str) -> None:
    with _diag_lock:
        _diag.pop(query, None)


def summarize(rows: list[tuple[float, str, Any, int, str]]) -> str:
    """Render rows as 'yahoo=ok-mobile-layout(334kB), brave=429-ratelimit(74kB), yahoo=results:7 ...' in call order."""
    return ", ".join(
        f"{e}={k}" if k.startswith("results:") else f"{e}={k}({s // 1000}kB)" for _, e, _st, s, k in rows
    ) or "no engine responses recorded"


# Plain-language wording for each response label, for the error a workflow user sees.
_KIND_WORDS = {
    "429-ratelimit": "rate-limited us (HTTP 429)",
    "403-forbidden": "refused us (HTTP 403)",
    "202-ratelimit": "rate-limited us (DuckDuckGo 202)",
    "captcha-page": "served a captcha / bot-check page",
    "throttle-page": "served its 'temporary problems' throttle page",
    "empty": "returned no results",
    "ok": "returned a page we could not parse",
    "ok-desktop": "returned a page we could not parse",
    "ok-mobile-layout": "returned a page we could not parse",
}


def _kind_words(kind: str) -> str:
    if kind in _KIND_WORDS:
        return _KIND_WORDS[kind]
    if kind.startswith("exception:Timeout"):
        return "did not answer in time"
    if kind.startswith("transport-drop") or kind.startswith("exception"):
        return "dropped the connection"
    if kind.isdigit():
        return f"answered HTTP {kind}"
    return kind


# Short labels for the per-engine table in the report a workflow user sees.
_SHORT_WORDS = {
    "429-ratelimit": "rate limited (HTTP 429)",
    "403-forbidden": "blocked (HTTP 403)",
    "202-ratelimit": "rate limited (DuckDuckGo 202)",
    "captcha-page": "bot-check page",
    "throttle-page": "throttled (temporary problems page)",
    "empty": "no results",
    "ok": "no results",
    "ok-desktop": "no results",
    "ok-mobile-layout": "no results",
}


def _short_words(kind: str) -> str:
    if kind in _SHORT_WORDS:
        return _SHORT_WORDS[kind]
    if kind.startswith("ok"):
        return "no results"
    if kind.startswith("exception:Timeout"):
        return "timed out"
    if kind.startswith("transport-drop") or kind.startswith("exception"):
        return "connection dropped"
    if kind.isdigit():
        return f"HTTP {kind}"
    return kind


def engine_lines(rows: list[tuple[float, str, Any, int, str]]) -> list[str]:
    """One aligned line per engine with its last response, e.g. 'brave       rate limited (HTTP 429)'."""
    last: dict[str, str] = {}
    for _ts, engine, _st, _size, kind in rows:
        if not kind.startswith("results:"):
            last[engine] = kind
    if not last:
        return ["(no engine responses recorded)"]
    width = max(len(e) for e in last) + 2
    return [f"{e.ljust(width)}{_short_words(k)}" for e, k in last.items()]


def verdict(rows: list[tuple[float, str, Any, int, str]]) -> tuple[str, str]:
    """(headline, per-engine detail) in plain language, from every engine response of a failed search.

    headline: one sentence saying why it failed (blocked / timeouts / genuinely no results).
    detail:   'brave rate-limited us (HTTP 429); yahoo served its throttle page; wikipedia returned no results'
    """
    last: dict[str, str] = {}
    for _ts, engine, _st, _size, kind in rows:
        if kind.startswith("results:"):
            continue
        last[engine] = kind  # keep the latest response per engine
    if not last:
        return "no search engine answered at all", "no engine responses recorded"
    blocked = [e for e, k in last.items() if k in BLOCK_KINDS or k.isdigit()]
    timed_out = [e for e, k in last.items() if "Timeout" in k or "transport" in k or k.startswith("exception")]
    if blocked and len(blocked) + len(timed_out) >= max(1, len(last) - len(REFERENCE_ONLY)):
        headline = "the search engines are blocking or rate-limiting this server"
    elif timed_out and len(timed_out) >= len(last) - len(REFERENCE_ONLY):
        headline = "the search engines did not answer in time"
    elif blocked or timed_out:
        headline = "some search engines blocked this server and the rest returned nothing"
    else:
        headline = "no search engine had results for this query"
    detail = "; ".join(f"{e} {_kind_words(k)}" for e, k in last.items())
    return headline, detail


REFERENCE_ONLY = {"wikipedia", "grokipedia"}  # encyclopedias: 'no results' from them is expected for web queries

# response labels that mean the engine served a real page (results or none) rather than a refusal
ANSWERED_KINDS = {"ok", "ok-desktop", "ok-mobile-layout", "empty"}


def answered_engines(rows: list[tuple[float, str, Any, int, str]]) -> set[str]:
    """Engines whose last response in ``rows`` was a proper page.

    An engine that served a page with no hits answers the same page when asked again, so a
    retry should not ask it; only blocked, throttled, timed-out or dropped engines can change
    their answer.
    """
    last: dict[str, str] = {}
    for _, engine, status, _size, kind in rows:
        if status == "RESULTS":
            continue
        last[engine] = kind
    return {e for e, k in last.items() if k in ANSWERED_KINDS}


# Per-engine outcome of one search, for the workflow to route on.
STATUS_SUCCESSFUL = "successful"   # the engine returned parsed results
STATUS_NO_RESULT = "no_result"     # the engine served a proper page with nothing on it
STATUS_BLOCKED = "blocked"         # refusal, bot-check, throttle page, timeout or dropped connection
STATUS_NOT_APPLIED = "not_applied"  # the engine was not asked (or had not answered when the search ended)

# The engines whose joint refusal means "this server cannot search right now"; a workflow may
# route to a paid search API only in that case, not when the engines simply had nothing.
PRIMARY_ENGINES = ("google", "yahoo", "brave")


def engine_status(
    rows: list[tuple[float, str, Any, int, str]], candidates: list[str] | None = None
) -> dict[str, str]:
    """Map each engine to STATUS_* from every response recorded for one search.

    ``candidates`` lists the engines the search could ask; those absent from ``rows`` are
    reported as not applied. Engines that appear in ``rows`` but not in ``candidates`` are
    reported too.
    """
    last: dict[str, str] = {}
    got_results: set[str] = set()
    for _ts, engine, status, _size, kind in rows:
        if status == "RESULTS":
            if kind.startswith("results:") and int(kind.split(":", 1)[1] or 0) > 0:
                got_results.add(engine)
            continue
        last[engine] = kind
    out: dict[str, str] = {}
    for engine in list(candidates or []) + [e for e in last if e not in (candidates or [])]:
        if engine in got_results:
            out[engine] = STATUS_SUCCESSFUL
        elif engine not in last:
            out[engine] = STATUS_NOT_APPLIED
        elif last[engine] in ANSWERED_KINDS or last[engine].startswith("ok("):
            out[engine] = STATUS_NO_RESULT
        else:
            out[engine] = STATUS_BLOCKED
    return out


def search_status(statuses: dict[str, str], primary: tuple[str, ...] = PRIMARY_ENGINES) -> str:
    """One word for the whole search: successful, blocked or no_result.

    ``blocked`` means every primary engine that was asked refused, timed out or dropped, and at
    least one was asked (an engine that was not asked does not count either way). Anything else
    without results is ``no_result``.
    """
    if any(v == STATUS_SUCCESSFUL for v in statuses.values()):
        return STATUS_SUCCESSFUL
    asked = [statuses[e] for e in primary if statuses.get(e, STATUS_NOT_APPLIED) != STATUS_NOT_APPLIED]
    if asked and all(v == STATUS_BLOCKED for v in asked):
        return STATUS_BLOCKED
    if not asked and statuses and all(v in (STATUS_BLOCKED, STATUS_NOT_APPLIED) for v in statuses.values())             and any(v == STATUS_BLOCKED for v in statuses.values()):
        return STATUS_BLOCKED
    return STATUS_NO_RESULT


def rotation(category: str) -> list[str] | None:
    """Engine names ddgs would ask for ``category`` on 'auto' (None when ddgs is not installed)."""
    try:
        from ddgs.engines import ENGINES
    except ImportError:
        return None
    return list(ENGINES.get(category, {}).keys())


def suppliers(rows: list[tuple[float, str, Any, int, str]]) -> str:
    """Engines that returned results, e.g. 'yahoo:7, brave:5' ('none' if no engine did)."""
    got = [(e, s) for _, e, _st, s, k in rows if k.startswith("results:") and s > 0]
    return ", ".join(f"{e}:{n}" for e, n in got) or "none"


# --- Google via curl_cffi ---------------------------------------------------------------
class _CffiResponse:
    """Minimal stand-in for ddgs.http_client.Response (status_code + text is all callers read)."""

    __slots__ = ("status_code", "text")

    def __init__(self, status_code: int, text: str) -> None:
        self.status_code, self.text = status_code, text


def _cffi_session(**kwargs: Any) -> Any:
    """Open a curl_cffi Session (separate so tests can substitute it). ImportError if not installed."""
    from curl_cffi import requests as cffi_requests

    return cffi_requests.Session(**kwargs)


def uses_curl_cffi(engine_name: str) -> bool:
    return GOOGLE_CURL_CFFI and engine_name in GOOGLE_ENGINES


def google_request(engine: Any, method: str, url: str, **kwargs: Any) -> _CffiResponse:
    """Send one Google request the way Google's /wml endpoint accepts it: old-Chrome TLS/header
    profile, browser default headers, the engine's own (feature-phone) User-Agent, no cookies.

    Proxy / timeout / verify follow what the caller gave ``DDGS(...)`` (captured on the engine's
    HttpClient by the constructor patch in ``apply``). Errors are mapped to ddgs's exception types so
    the transport retry and the caller's handling stay unchanged.
    """
    from ddgs.exceptions import DDGSException, TimeoutException

    client = getattr(engine, "http_client", None)
    proxy = getattr(client, "proxy", None)
    timeout = getattr(client, "timeout", None) or 10
    verify = getattr(client, "verify", True)
    headers = dict(getattr(engine, "headers_update", {}) or {})
    headers.update(kwargs.pop("headers", None) or {})
    kwargs.pop("cookies", None)  # never send cookies to Google (CONSENT=YES+ alone draws the sorry page)
    session_kwargs: dict[str, Any] = {
        "impersonate": GOOGLE_IMPERSONATE,
        "default_headers": True,
        "discard_cookies": True,
        "verify": verify if isinstance(verify, bool) else True,
        "timeout": timeout,
    }
    if proxy:
        session_kwargs["proxies"] = {"http": proxy, "https": proxy}
    try:
        with _cffi_session(**session_kwargs) as session:
            resp = session.request(method, url, headers=headers, **kwargs)
            return _CffiResponse(int(resp.status_code), resp.text or "")
    except ImportError:
        raise  # curl_cffi not installed: the caller falls back to primp
    except Exception as ex:
        name = type(ex).__name__
        if "Timeout" in name or "timed out" in str(ex).lower() or "curl: (28)" in str(ex):
            raise TimeoutException(ex) from ex
        raise DDGSException(f"RequestError: {name}: {ex!r}") from ex


# --- patches --------------------------------------------------------------------------
_applied = False


def apply() -> None:
    """Install the patches into ddgs (idempotent)."""
    global _applied
    if _applied:
        return
    _applied = True

    try:
        import ddgs.http_client as hc
        from ddgs.base import BaseSearchEngine
    except ImportError as ex:  # e.g. unit tests running with the ddgs stub
        logger.warning("ddgs hardening not applied: %s", ex)
        return

    # 1. desktop fingerprint (+ remember proxy/timeout/verify for the curl_cffi Google path)
    _orig_init = hc.HttpClient.__init__

    def __init__(self: Any, proxy: str | None = None, timeout: int | None = 10, *, verify: bool | str = True) -> None:
        self.proxy, self.timeout, self.verify = proxy, timeout, verify
        if not DESKTOP_FINGERPRINT:
            _orig_init(self, proxy=proxy, timeout=timeout, verify=verify)
            return
        import primp

        self.client = primp.Client(
            proxy=proxy,
            timeout=timeout,
            impersonate="random",
            impersonate_os=random.choice(DESKTOP_OS_CHOICES),
            verify=verify if isinstance(verify, bool) else True,
            ca_cert_file=verify if isinstance(verify, str) else None,
        )

    hc.HttpClient.__init__ = __init__  # type: ignore[method-assign]

    # 5. Google through curl_cffi (see module docstring); every other engine keeps primp
    def _send(self: Any, *a: Any, **k: Any) -> Any:
        if uses_curl_cffi(self.name):
            try:
                return google_request(self, *a, **k)
            except ImportError as ex:  # curl_cffi not installed: primp, which Google will refuse
                logger.warning("google: curl_cffi unavailable (%s); falling back to primp", ex)
        return self.http_client.request(*a, **k)

    # 3. diagnostics: know which engine/query runs in this worker thread, record each response
    if ENGINE_DIAGNOSTICS:
        _orig_search = BaseSearchEngine.search

        def search(self: Any, query: str, *a: Any, **k: Any) -> Any:
            _local.engine, _local.query = self.name, query
            try:
                results = _orig_search(self, query, *a, **k)
                n = len(results or [])
                if n:
                    # a page that parsed into results was a results page, whatever words it contained
                    # (Brave's results page mentions "captcha" in its scripts and was labelled captcha-page)
                    _relabel_blocks_as_ok(query, self.name)
                # which engine actually supplied results (successful searches log this too)
                _record(query, self.name, "RESULTS", n, f"results:{n}")
                return results
            except Exception as ex:
                _record(query, self.name, "EXC", 0, f"exception:{type(ex).__name__}")
                raise
            finally:
                _local.engine = _local.query = None

        BaseSearchEngine.search = search  # type: ignore[method-assign]

    # request override: transport retry (4), Google via curl_cffi (5), response classification (3).
    # Installed regardless of the diagnostics switch; _record stores nothing when no query is tracked.
    def request(self: Any, *a: Any, **k: Any) -> Any:
        query = getattr(_local, "query", None)
        for extra in range(TRANSPORT_RETRIES + 1):
            try:
                resp = _send(self, *a, **k)
                break
            except Exception as ex:
                if extra >= TRANSPORT_RETRIES or not is_transport_error(ex):
                    raise
                _record(query, self.name, "EXC", 0, "transport-drop-retried")
                logger.warning(
                    "%s: connection dropped (%s); re-sending (%d/%d)",
                    self.name, str(ex)[:120], extra + 1, TRANSPORT_RETRIES,
                )
                time.sleep(TRANSPORT_RETRY_DELAY_SECONDS * (extra + 1) + random.uniform(0, 0.3))
        body = resp.text or ""
        kind = classify(self.name, resp.status_code, body)
        _record(getattr(_local, "query", None), self.name, resp.status_code, len(body), kind)
        return body if resp.status_code == 200 else None

    BaseSearchEngine.request = request  # type: ignore[method-assign]

    # 2. Yahoo mobile-layout parser
    if YAHOO_MOBILE_PARSER:
        from ddgs.engines.yahoo import Yahoo

        _orig_extract = Yahoo.extract_results
        mobile_items = (
            "//section[contains(@class,'algo-sr')]"
            " | //div[contains(@class,'grp-talgo') and .//a[contains(@class,'s-title')]]"
        )
        title_anchor = ".//a[contains(concat(' ',normalize-space(@class),' '),' s-title ')]"

        def extract_results(self: Any, html_text: str) -> list[Any]:
            results = _orig_extract(self, html_text)
            if results:
                return results
            tree = self.extract_tree(self.pre_process_html(html_text))
            out, seen = [], set()
            for item in tree.xpath(mobile_items):
                anchors = item.xpath(title_anchor)
                if not anchors:
                    continue
                href = anchors[0].get("href") or ""
                title = " ".join("".join(anchors[0].xpath("./text()")).split())
                body = " ".join("".join(item.xpath(".//p[contains(@class,'s-desc')]//text()")).split())
                key = href.split("/RU=", 1)[1][:80] if "/RU=" in href else href
                if not href or not title or key in seen:
                    continue
                seen.add(key)
                r = self.result_type()
                r.title, r.href, r.body = title, href, body
                out.append(r)
            if out:
                logger.info("yahoo: parsed %d results from the mobile layout", len(out))
            return out

        Yahoo.extract_results = extract_results  # type: ignore[method-assign]

    # 6. engine fan-out
    if ENGINE_FANOUT:
        _install_fanout()

    # 7. drop engines no HTTP client can pass
    if DISABLED_ENGINES:
        from ddgs.engines import ENGINES

        for category in ENGINES.values():
            for name in DISABLED_ENGINES:
                if category.pop(name, None) is not None:
                    logger.info("ddgs engine %s removed from the rotation", name)


# ---- engine fan-out ---------------------------------------------------------------------

_fanout_installed = False
_fanout_executor: Any = None
_fanout_lock = threading.Lock()


def fanout_active() -> bool:
    """True when searches run through the fan-out (the caller must then not wrap them in a worker thread)."""
    return ENGINE_FANOUT and _fanout_installed


def _gevent_threading_patched() -> bool:
    try:
        from gevent import monkey
    except ImportError:
        return False
    return bool(monkey.is_module_patched("threading"))


class _Handle:
    """Uniform ready()/get() over a gevent AsyncResult or a concurrent.futures Future.

    The task returns ``(outcome, value)``; ``get()`` re-raises a captured exception. Capturing it in
    the task keeps an engine that fails after the search has already returned from being reported
    as an unhandled error by the pool.
    """

    def __init__(self, obj: Any) -> None:
        self._o = obj

    def ready(self) -> bool:
        return self._o.ready() if hasattr(self._o, "ready") else self._o.done()

    def get(self) -> Any:
        outcome, value = self._o.get() if hasattr(self._o, "get") else self._o.result()
        if outcome == "err":
            raise value
        return value


def _captured(fn: Any, *args: Any, **kwargs: Any) -> tuple[str, Any]:
    try:
        return "ok", fn(*args, **kwargs)
    except Exception as ex:  # noqa: BLE001 - handed back to the caller through _Handle.get()
        return "err", ex


def _spawn_real(fn: Any, *args: Any, **kwargs: Any) -> _Handle:
    """Run fn on a real OS thread (gevent's native pool when the process is monkey-patched)."""
    global _fanout_executor
    if _gevent_threading_patched():
        import gevent

        pool = gevent.get_hub().threadpool
        if pool.maxsize < FANOUT_THREADS:
            pool.maxsize = FANOUT_THREADS
        return _Handle(pool.spawn(_captured, fn, *args, **kwargs))
    with _fanout_lock:
        if _fanout_executor is None:
            from concurrent.futures import ThreadPoolExecutor

            _fanout_executor = ThreadPoolExecutor(max_workers=FANOUT_THREADS, thread_name_prefix="DDGSfan")
    return _Handle(_fanout_executor.submit(_captured, fn, *args, **kwargs))


def fanout_search(
    engines: list[Any],
    query: str,
    *,
    max_results: int | None,
    timeout: float | None,
    search_kwargs: dict[str, Any],
) -> list[dict[str, Any]]:
    """Ask every engine at once; return once the pooled results reach max_results.

    Mirrors ddgs' result handling (one engine per provider, de-duplication by link, ranking,
    TimeoutException when the last error was a timeout) but without the round-by-round wait.
    """
    from ddgs.exceptions import DDGSException, TimeoutException
    from ddgs.results import ResultsAggregator
    from ddgs.similarity import SimpleFilterRanker

    aggregator: Any = ResultsAggregator({"href", "image", "url", "embed_url"})
    seen_providers: set[str] = set()
    pending: list[tuple[Any, _Handle]] = []
    for engine in engines:
        if engine.provider in seen_providers:
            continue
        seen_providers.add(engine.provider)
        pending.append((engine, _spawn_real(engine.search, query, **search_kwargs)))

    deadline = time.monotonic() + float(timeout or 10) + 1.0
    err: BaseException | None = None
    while pending:
        still: list[tuple[Any, _Handle]] = []
        for engine, handle in pending:
            if not handle.ready():
                still.append((engine, handle))
                continue
            try:
                if r := handle.get():
                    aggregator.extend(r)
            except Exception as ex:  # noqa: BLE001 - same policy as upstream: remember, keep going
                err = ex
                logger.info("Error in engine %s: %r", engine.name, ex)
        pending = still
        if max_results and len(aggregator) >= max_results:
            break
        if not pending or time.monotonic() > deadline:
            break
        time.sleep(FANOUT_POLL_SECONDS)

    results = SimpleFilterRanker().rank(aggregator.extract_dicts(), query)
    if results:
        return results[:max_results] if max_results else results
    if "timed out" in f"{err}":
        raise TimeoutException(err)
    raise DDGSException(err or "No results found.")


def _install_fanout() -> None:
    global _fanout_installed
    # The package's top-level ``DDGS`` is a lazy proxy class: an attribute assigned on it stays on
    # the proxy and never reaches the real class that instances are built from. Patch the real one.
    from ddgs.ddgs import DDGS
    from ddgs.exceptions import DDGSException

    def _search_sync(  # noqa: PLR0913
        self: Any,
        category: str,
        query: str | None = None,
        keywords: str | None = None,
        *,
        region: str = "us-en",
        safesearch: str = "moderate",
        timelimit: str | None = None,
        max_results: int | None = 10,
        page: int = 1,
        backend: str = "auto",
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        query = keywords or query
        if not query:
            msg = "query is mandatory."
            raise DDGSException(msg)
        engines = self._get_engines(category, backend)
        return fanout_search(
            engines,
            query,
            max_results=max_results,
            timeout=self._timeout,
            search_kwargs={"region": region, "safesearch": safesearch, "timelimit": timelimit, "page": page, **kwargs},
        )

    DDGS._search_sync = _search_sync  # type: ignore[method-assign]
    _fanout_installed = True

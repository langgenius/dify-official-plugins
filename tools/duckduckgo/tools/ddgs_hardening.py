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
4. DDG_ENGINE_COOLDOWN_SECONDS  engines that just answered 429/403/202/captcha are left out
                                of the next auto-mode attempts for this many seconds
                                (0 = off), so retries go to engines that can still answer.
5. DDG_TRANSPORT_RETRIES        re-send a request whose connection was dropped by the engine
                                ("peer closed connection without sending TLS close_notify",
                                seen from Yahoo under concurrency) after a short pause, instead
                                of failing the whole attempt (0 = off).
"""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


# --- settings -------------------------------------------------------------------------
def _flag(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() not in ("0", "false", "no", "off", "")


DESKTOP_FINGERPRINT = _flag("DDG_DESKTOP_FINGERPRINT")
DESKTOP_OS_CHOICES = ("windows", "macos")  # linux showed a few throttle pages; windows/macos showed none
YAHOO_MOBILE_PARSER = _flag("DDG_YAHOO_MOBILE_PARSER")
ENGINE_DIAGNOSTICS = _flag("DDG_ENGINE_DIAGNOSTICS")
ENGINE_COOLDOWN_SECONDS = float(os.environ.get("DDG_ENGINE_COOLDOWN_SECONDS", "60"))
# 5. Transport-level retry: Yahoo drops HTTP/2 connections under concurrency ("peer closed
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

# statuses/pages that mean "this engine is blocking this host right now"
BLOCK_KINDS = {"429-ratelimit", "403-forbidden", "202-ratelimit", "captcha-page", "throttle-page"}


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
_cooldown_until: dict[str, float] = {}  # engine name -> monotonic deadline


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
        if ENGINE_COOLDOWN_SECONDS > 0 and kind in BLOCK_KINDS:
            _cooldown_until[engine] = now + ENGINE_COOLDOWN_SECONDS


def diagnostics_for(query: str, since: float | None = None) -> list[tuple[float, str, Any, int, str]]:
    with _diag_lock:
        rows = list(_diag.get(query, []))
    return [r for r in rows if since is None or r[0] >= since]


def clear_diagnostics(query: str) -> None:
    with _diag_lock:
        _diag.pop(query, None)


def summarize(rows: list[tuple[float, str, Any, int, str]]) -> str:
    """Render rows as 'yahoo=ok-mobile-layout(334kB), brave=429-ratelimit(74kB), ...' in call order."""
    return ", ".join(f"{e}={k}({s // 1000}kB)" for _, e, _st, s, k in rows) or "no engine responses recorded"


def engines_in_cooldown() -> set[str]:
    now = time.monotonic()
    with _diag_lock:
        return {e for e, t in _cooldown_until.items() if t > now}


def healthy_backend(category: str) -> str | None:
    """Comma list of engines for `category` not in cooldown, or None to keep ddgs 'auto'."""
    if ENGINE_COOLDOWN_SECONDS <= 0:
        return None
    try:
        from ddgs.engines import ENGINES
    except Exception:  # pragma: no cover
        return None
    names = [n for n, cls in ENGINES.get(category, {}).items() if not getattr(cls, "disabled", False)]
    down = engines_in_cooldown()
    healthy = [n for n in names if n not in down]
    if not names or not down or not healthy:
        return None
    return ",".join(healthy)


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

    # 1. desktop fingerprint
    if DESKTOP_FINGERPRINT:
        import primp

        def __init__(self: Any, proxy: str | None = None, timeout: int | None = 10, *, verify: bool | str = True) -> None:
            self.client = primp.Client(
                proxy=proxy,
                timeout=timeout,
                impersonate="random",
                impersonate_os=random.choice(DESKTOP_OS_CHOICES),
                verify=verify if isinstance(verify, bool) else True,
                ca_cert_file=verify if isinstance(verify, str) else None,
            )

        hc.HttpClient.__init__ = __init__  # type: ignore[method-assign]

    # 3. diagnostics: know which engine/query runs in this worker thread, record each response
    if ENGINE_DIAGNOSTICS or ENGINE_COOLDOWN_SECONDS > 0:
        _orig_search = BaseSearchEngine.search

        def search(self: Any, query: str, *a: Any, **k: Any) -> Any:
            _local.engine, _local.query = self.name, query
            try:
                return _orig_search(self, query, *a, **k)
            except Exception as ex:
                _record(query, self.name, "EXC", 0, f"exception:{type(ex).__name__}")
                raise
            finally:
                _local.engine = _local.query = None

        def request(self: Any, *a: Any, **k: Any) -> Any:
            query = getattr(_local, "query", None)
            for extra in range(TRANSPORT_RETRIES + 1):
                try:
                    resp = self.http_client.request(*a, **k)
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

        BaseSearchEngine.search = search  # type: ignore[method-assign]
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

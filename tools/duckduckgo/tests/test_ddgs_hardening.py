"""Tests for tools/ddgs_hardening.py. Need the real ``ddgs`` package (they patch its classes);
skipped when only the stub from test_ddgs_utils is present."""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ddgs = pytest.importorskip("ddgs")
pytest.importorskip("lxml")
if isinstance(ddgs, types.ModuleType) and getattr(ddgs, "__file__", None) is None:
    # the in-memory stub installed by test_ddgs_utils when ddgs is not installed
    pytest.skip("real ddgs package required", allow_module_level=True)
pytest.importorskip("ddgs.http_client")

from ddgs.base import BaseSearchEngine  # noqa: E402
from ddgs.engines.yahoo import Yahoo  # noqa: E402
from ddgs.exceptions import DDGSException  # noqa: E402

from tools import ddgs_hardening  # noqa: E402

ddgs_hardening.apply()


class _Resp:
    def __init__(self, status: int, text: str) -> None:
        self.status_code, self.text = status, text


class _FlakyClient:
    """Drops the connection ``drops`` times, then answers 200."""

    def __init__(self, drops: int, body: str = "<html>ok</html>") -> None:
        self.drops, self.body, self.calls = drops, body, 0

    def request(self, *a, **k):
        self.calls += 1
        if self.calls <= self.drops:
            raise DDGSException(
                "RequestError: RequestError('error sending request for url (https://search.yahoo.com/...) "
                "> peer closed connection without sending TLS close_notify')"
            )
        return _Resp(200, self.body)


@pytest.fixture
def fast_sleep(monkeypatch):
    monkeypatch.setattr(ddgs_hardening.time, "sleep", lambda s: None)


def test_transport_drop_is_resent_within_the_same_engine_call(fast_sleep):
    engine = Yahoo()
    engine.http_client = _FlakyClient(drops=1)
    assert BaseSearchEngine.request(engine, "GET", "https://search.yahoo.com/search") == "<html>ok</html>"
    assert engine.http_client.calls == 2


def test_transport_drop_gives_up_after_configured_retries(fast_sleep, monkeypatch):
    monkeypatch.setattr(ddgs_hardening, "TRANSPORT_RETRIES", 2)
    engine = Yahoo()
    engine.http_client = _FlakyClient(drops=5)
    with pytest.raises(DDGSException):
        BaseSearchEngine.request(engine, "GET", "https://search.yahoo.com/search")
    assert engine.http_client.calls == 3  # 1 + 2 retries


def test_non_transport_errors_are_not_retried(fast_sleep):
    class _Client:
        calls = 0

        def request(self, *a, **k):
            self.calls += 1
            raise DDGSException("proxy refused the connection: 407")

    engine = Yahoo()
    engine.http_client = _Client()
    with pytest.raises(DDGSException):
        BaseSearchEngine.request(engine, "GET", "https://search.yahoo.com/search")
    assert engine.http_client.calls == 1


@pytest.mark.parametrize(
    ("engine", "status", "body", "expected"),
    [
        ("brave", 429, "<html>captcha</html>", "429-ratelimit"),
        ("mojeek", 403, "", "403-forbidden"),
        ("duckduckgo", 202, "<html></html>", "202-ratelimit"),
        ("yahoo", 200, "<html>We had temporary problems searching for web pages.</html>", "throttle-page"),
        ("startpage", 200, "<html>please solve this captcha</html>", "captcha-page"),
        ("yahoo", 200, "<div class='dd algo relsrch'>…</div>", "ok-desktop"),
        ("yahoo", 200, "<section class='dd algo-sr'>…</section>", "ok-mobile-layout"),
    ],
)
def test_classify(engine, status, body, expected):
    assert ddgs_hardening.classify(engine, status, body) == expected


MOBILE_PAGE = """
<html><body>
<section class="dd fst algo s-algo algo-sr Sr">
  <div class="grp grp-talgo ag-1 u-tapHgt cur-p"><div class="compTitle p-r">
    <h3 class="title d-ib mt-42"><a class="s-title fz-m" href="https://r.search.yahoo.com/_ylt=x/RU=https%3a%2f%2fen.wikipedia.org%2fwiki%2fNan_Fung_Group/RK=2/RS=y">
      <span class="title-url">Wikipedia https://en.m.wikipedia.org</span>Nan Fung Group - Wikipedia</a></h3>
  </div></div>
  <div class="grp grp-talgo-ext"><p class="s-desc lh-20">Nan Fung Group is a privately held group of companies.</p></div>
</section>
<section class="dd lst algo s-algo algo-sr Sr">
  <div class="grp grp-talgo ag-2"><div class="compTitle p-r">
    <h3 class="title"><a class="s-title fz-m" href="https://r.search.yahoo.com/_ylt=y/RU=https%3a%2f%2fwww.nanfung.com/RK=2/RS=z">
      <span class="title-url">Nan Fung Group https://www.nanfung.com</span>Home - Nan Fung Group</a></h3>
  </div></div>
  <p class="s-desc">Founded in 1954.</p>
</section>
</body></html>
"""


def test_yahoo_mobile_layout_is_parsed():
    results = Yahoo().extract_results(MOBILE_PAGE)
    assert [r.title for r in results] == ["Nan Fung Group - Wikipedia", "Home - Nan Fung Group"]
    assert results[0].body.startswith("Nan Fung Group is a privately held")
    assert "/RU=" in results[0].href


def test_desktop_layout_still_uses_the_stock_parser():
    page = "<html><div class='dd algo relsrch'><div class='compTitle Title'><h3>T</h3><a href='https://r.search.yahoo.com/RU=https%3a%2f%2fx.com/RK=2/RS=1'>t</a></div><div class='compText Text'>B</div></div></html>"
    results = Yahoo().extract_results(page)
    assert len(results) == 1 and results[0].title == "T"


def test_cooldown_excludes_blocked_engines(monkeypatch):
    monkeypatch.setattr(ddgs_hardening, "_cooldown_until", {})
    monkeypatch.setattr(ddgs_hardening, "ENGINE_COOLDOWN_SECONDS", 60.0)
    assert ddgs_hardening.healthy_backend("text") is None  # nothing blocked -> leave 'auto'
    ddgs_hardening._record("q", "brave", 429, 10, "429-ratelimit")
    ddgs_hardening._record("q", "google", 429, 10, "429-ratelimit")
    healthy = ddgs_hardening.healthy_backend("text")
    assert healthy is not None
    assert "brave" not in healthy.split(",") and "google" not in healthy.split(",")
    assert "yahoo" in healthy.split(",")

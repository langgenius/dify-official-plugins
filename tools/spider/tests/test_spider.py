"""Request shape and error handling for the Spider plugin. No network calls."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

PLUGIN_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_DIR))

import spiderApp  # noqa: E402
from dify_plugin.errors.tool import ToolProviderCredentialValidationError  # noqa: E402
from provider.spider import SpiderProvider  # noqa: E402
from spiderApp import Spider, SpiderError  # noqa: E402
from tools.scraper_crawler import ScrapeTool, build_options, parse_patterns  # noqa: E402


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


@pytest.fixture
def calls(monkeypatch):
    recorded: list[dict] = []
    queue: list[FakeResponse] = []

    def fake_post(url, headers=None, json=None, stream=False, timeout=None):
        recorded.append({"method": "POST", "url": url, "json": json, "timeout": timeout})
        return queue.pop(0) if queue else FakeResponse(payload=[])

    def fake_get(url, headers=None, stream=False, timeout=None):
        recorded.append({"method": "GET", "url": url, "timeout": timeout})
        return queue.pop(0) if queue else FakeResponse(payload={"data": {"credits": 1}})

    monkeypatch.setattr(spiderApp.requests, "post", fake_post)
    monkeypatch.setattr(spiderApp.requests, "get", fake_get)
    return recorded, queue


def make_tool(api_key="test-key"):
    tool = ScrapeTool.__new__(ScrapeTool)
    tool.runtime = SimpleNamespace(credentials={"spider_api_key": api_key})
    tool.create_text_message = lambda text: text
    return tool


def test_scrape_mode_calls_scrape_endpoint(calls):
    recorded, queue = calls
    queue.append(FakeResponse(payload=[{"url": "https://example.com", "content": "# Hi"}]))
    out = list(make_tool()._invoke({"url": "https://example.com", "mode": "scrape", "limit": 5}))
    assert recorded[0]["url"] == "https://api.spider.cloud/v1/scrape"
    body = recorded[0]["json"]
    assert body["url"] == "https://example.com"
    assert body["return_format"] == "markdown"
    assert "limit" not in body and "depth" not in body
    assert out == ["URL: https://example.com\nCONTENT: # Hi\n\n"]


def test_crawl_mode_sends_patterns_as_arrays(calls):
    recorded, _ = calls
    list(
        make_tool()._invoke(
            {
                "url": "https://example.com",
                "mode": "crawl",
                "limit": 3,
                "depth": 2,
                "blacklist": "/blog/*, /about",
                "whitelist": "/docs/",
            }
        )
    )
    assert recorded[0]["url"] == "https://api.spider.cloud/v1/crawl"
    body = recorded[0]["json"]
    assert body["limit"] == 3
    assert body["depth"] == 2
    assert body["blacklist"] == ["/blog/*", "/about"]
    assert body["whitelist"] == ["/docs/"]
    assert recorded[0]["timeout"] is not None


def test_defaults_bound_the_crawl():
    options = build_options({"url": "https://example.com"})
    assert options["limit"] == 10
    assert options["depth"] == 25
    assert "blacklist" not in options and "whitelist" not in options


@pytest.mark.parametrize(
    ("raw", "limit"),
    [(0, 0), ("0", 0), (0.5, 1), ("2.2", 3), (-1, 10), ("abc", 10), (float("inf"), 10), (float("nan"), 10)],
)
def test_only_an_explicit_zero_is_unlimited(raw, limit):
    assert build_options({"url": "https://example.com", "limit": raw})["limit"] == limit


def test_parse_patterns_drops_empty_items():
    assert parse_patterns(" , ,") is None
    assert parse_patterns(None) is None
    assert parse_patterns(["/a", " "]) == ["/a"]


def test_request_fields_match_current_api():
    fields = spiderApp.RequestParamsDict.__annotations__
    for gone in ("anti_bot", "gpt_config", "store_data", "proxy_enabled"):
        assert gone not in fields
    assert "blacklist" in fields and "whitelist" in fields
    assert not hasattr(Spider, "extract_contacts")
    assert not hasattr(Spider, "label")


def test_null_content_does_not_crash(calls):
    _, queue = calls
    queue.append(FakeResponse(payload=[{"url": "https://example.com", "content": None}]))
    out = list(make_tool()._invoke({"url": "https://example.com", "mode": "scrape"}))
    assert out == ["URL: https://example.com\nCONTENT: \n\n"]


def test_error_yields_one_message(calls):
    _, queue = calls
    queue.append(FakeResponse(status_code=402, payload={"error": "Your credit balance is empty."}))
    out = list(make_tool()._invoke({"url": "https://example.com", "mode": "crawl"}))
    assert len(out) == 1
    assert "credit balance is empty" in out[0]


def test_error_with_empty_body(calls):
    _, queue = calls
    queue.append(FakeResponse(status_code=500))
    with pytest.raises(SpiderError) as err:
        Spider(api_key="k").crawl_url("https://example.com")
    assert err.value.status_code == 500


def test_get_credits_uses_data_credits(calls):
    recorded, _ = calls
    Spider(api_key="k").get_credits()
    assert recorded == [
        {"method": "GET", "url": "https://api.spider.cloud/v1/data/credits", "timeout": spiderApp.REQUEST_TIMEOUT}
    ]


def test_validation_does_not_scrape(calls):
    recorded, _ = calls
    SpiderProvider.__new__(SpiderProvider)._validate_credentials({"spider_api_key": "k"})
    assert [c["method"] for c in recorded] == ["GET"]
    assert recorded[0]["url"].endswith("/data/credits")


def test_validation_rejects_bad_key(calls):
    _, queue = calls
    queue.append(FakeResponse(status_code=401))
    with pytest.raises(ToolProviderCredentialValidationError):
        SpiderProvider.__new__(SpiderProvider)._validate_credentials({"spider_api_key": "bad"})


def test_validation_rejects_missing_key(calls):
    with pytest.raises(ToolProviderCredentialValidationError):
        SpiderProvider.__new__(SpiderProvider)._validate_credentials({"spider_api_key": ""})


def test_yaml_files_parse_and_link():
    manifest = yaml.safe_load((PLUGIN_DIR / "manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["author"] == "langgenius"
    provider = yaml.safe_load((PLUGIN_DIR / "provider" / "spider.yaml").read_text(encoding="utf-8"))
    for rel in provider["tools"]:
        tool = yaml.safe_load((PLUGIN_DIR / rel).read_text(encoding="utf-8"))
        names = {p["name"] for p in tool["parameters"]}
        assert {"url", "mode", "limit", "depth", "blacklist", "whitelist", "readability"} <= names

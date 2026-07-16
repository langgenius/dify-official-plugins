import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.firecrawl_appx import FirecrawlApp


class _MessageToolMixin:
    def create_json_message(self, value):
        return {"type": "json", "value": value}

    def create_text_message(self, value):
        return {"type": "text", "value": value}


def test_firecrawl_app_search_posts_to_v2_search(monkeypatch):
    captured = {}

    def fake_request(self, method, url, data=None, headers=None):
        captured.update({"method": method, "url": url, "data": data, "headers": headers})
        return {"success": True, "data": {"web": []}}

    monkeypatch.setattr(FirecrawlApp, "_request", fake_request)

    app = FirecrawlApp(api_key="x", base_url="https://example.test")
    result = app.search(query="firecrawl docs", limit=3, sources=["web"])

    assert result == {"success": True, "data": {"web": []}}
    assert captured == {
        "method": "POST",
        "url": "https://example.test/v2/search",
        "data": {"query": "firecrawl docs", "limit": 3, "sources": ["web"]},
        "headers": None,
    }


def test_search_tool_builds_payload_and_returns_json(monkeypatch):
    from tools.search import SearchTool

    captured = {}

    def fake_search(self, query, **kwargs):
        captured.update({"query": query, "kwargs": kwargs})
        return {"success": True, "data": {"web": [{"url": "https://firecrawl.dev"}]}}

    monkeypatch.setattr(FirecrawlApp, "search", fake_search)

    tool = object.__new__(SearchTool)
    tool.runtime = SimpleNamespace(credentials={"firecrawl_api_key": "x", "base_url": "https://example.test"})
    tool.create_json_message = _MessageToolMixin.create_json_message.__get__(tool, SearchTool)
    tool.create_text_message = _MessageToolMixin.create_text_message.__get__(tool, SearchTool)

    messages = list(
        tool._invoke(
            {
                "query": "Firecrawl API",
                "limit": 5,
                "sources": "web,news",
                "categories": "github,research",
                "includeDomains": "firecrawl.dev,docs.firecrawl.dev",
                "country": "JP",
                "scrapeFormats": "markdown,summary",
                "onlyMainContent": True,
            }
        )
    )

    assert captured == {
        "query": "Firecrawl API",
        "kwargs": {
            "limit": 5,
            "sources": ["web", "news"],
            "categories": ["github", "research"],
            "includeDomains": ["firecrawl.dev", "docs.firecrawl.dev"],
            "country": "JP",
            "scrapeOptions": {"formats": [{"type": "markdown"}, {"type": "summary"}], "onlyMainContent": True},
        },
    }
    assert messages == [{"type": "json", "value": {"success": True, "data": {"web": [{"url": "https://firecrawl.dev"}]}}}]


def test_search_tool_omits_scrape_options_without_scrape_formats_and_trims_arrays(monkeypatch):
    from tools.search import SearchTool

    captured = {}

    def fake_search(self, query, **kwargs):
        captured.update({"query": query, "kwargs": kwargs})
        return {"success": True, "data": {"web": []}}

    monkeypatch.setattr(FirecrawlApp, "search", fake_search)

    tool = object.__new__(SearchTool)
    tool.runtime = SimpleNamespace(credentials={"firecrawl_api_key": "x", "base_url": "https://example.test"})
    tool.create_json_message = _MessageToolMixin.create_json_message.__get__(tool, SearchTool)
    tool.create_text_message = _MessageToolMixin.create_text_message.__get__(tool, SearchTool)

    list(
        tool._invoke(
            {
                "query": "Firecrawl API",
                "sources": "web, news",
                "categories": "github, research",
                "enterprise": "anon, zdr",
                "onlyMainContent": False,
            }
        )
    )

    assert captured == {
        "query": "Firecrawl API",
        "kwargs": {
            "limit": 10,
            "sources": ["web", "news"],
            "categories": ["github", "research"],
            "enterprise": ["anon", "zdr"],
        },
    }

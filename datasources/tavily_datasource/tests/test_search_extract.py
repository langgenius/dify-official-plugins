import json
import sys
from pathlib import Path

import pytest
import requests
from dify_plugin.entities.datasource import DatasourceRuntime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from datasources.search_extract import TavilySearchExtractDatasource


@pytest.fixture
def fixture(monkeypatch):
    calls = []
    responses = {"search": {"results": []}, "extract": {"results": []}}
    monkeypatch.setattr("socket.socket.connect", lambda *a, **k: pytest.fail("Unexpected network"))
    def send(session, request, **kwargs):
        calls.append((request, json.loads(request.body), kwargs))
        payload = responses[request.url.rsplit("/", 1)[1]]
        if isinstance(payload, Exception):
            raise payload
        response = requests.Response()
        response.status_code = 200
        response.request = request
        response._content = json.dumps(payload).encode()
        return response
    monkeypatch.setattr(requests.Session, "send", send)
    return calls, responses


def crawl(params):
    runtime = DatasourceRuntime(credentials={"tavily_api_key": "test-key"}, user_id=None, session_id=None)
    source = TavilySearchExtractDatasource(runtime, None)
    # Serialize each yielded framework message before the shared progress object changes.
    return [message.model_dump(mode="json") for message in source.website_crawl({"query": "q", "include_answer": False, **params})]


def final(messages):
    return messages[-1]["result"]


@pytest.mark.parametrize("raw", ["FULL DOCUMENT", "  full with spaces  "])
def test_requested_raw_content_wins_over_snippet(fixture, raw):
    calls, responses = fixture
    responses["search"]["results"] = [{"url": "https://example.test/a", "title": "Title", "content": "short snippet", "raw_content": raw}]
    result = final(crawl({"include_raw_content": True}))
    assert result["web_info_list"][0]["content"] == raw
    assert result["web_info_list"][0]["source_url"] == "https://example.test/a"
    assert len(calls) == 1


@pytest.mark.parametrize("raw", [None, "", "  "])
def test_snippet_is_safe_fallback_without_extra_extract_call(fixture, raw):
    calls, responses = fixture
    responses["search"]["results"] = [{"url": "https://example.test/a", "content": "snippet", "raw_content": raw}]
    result = final(crawl({"include_raw_content": True}))
    assert result["web_info_list"][0]["content"] == "snippet"
    assert "snippet" in result["web_info_list"][0]["description"].lower()
    assert len(calls) == 1


def test_raw_content_false_keeps_snippet_and_never_extracts(fixture):
    calls, responses = fixture
    responses["search"]["results"] = [{"url": "https://example.test/a", "content": "snippet", "raw_content": "full"}]
    result = final(crawl({"include_raw_content": False}))
    assert result["web_info_list"][0]["content"] == "snippet"
    assert calls[0][1]["include_raw_content"] is False
    assert len(calls) == 1


@pytest.mark.parametrize("content", [None, "", "   "])
def test_extract_only_when_neither_search_content_is_usable(fixture, content):
    calls, responses = fixture
    responses["search"]["results"] = [{"url": "https://example.test/a", "content": content, "raw_content": content}]
    responses["extract"] = {"results": [{"url": "https://example.test/a", "raw_content": "EXTRACTED"}]}
    result = final(crawl({"include_raw_content": True}))
    assert result["web_info_list"][0]["content"] == "EXTRACTED"
    assert len(calls) == 2


def test_partial_extract_failure_retains_url_and_failure_metadata(fixture):
    calls, responses = fixture
    responses["search"]["results"] = [
        {"url": "https://example.test/ok", "content": "snippet", "raw_content": "FULL"},
        {"url": "https://example.test/failed", "title": "Failed page", "content": ""},
    ]
    responses["extract"] = {"results": [], "failed_results": [{"url": "https://example.test/failed", "error": "Page unavailable"}], "request_id": "extract-123"}
    result = final(crawl({"include_raw_content": True}))
    assert result["web_info_list"][0]["content"] == "FULL"
    failed = result["web_info_list"][1]
    assert failed["source_url"] == "https://example.test/failed"
    assert failed["content"] == ""
    assert "Page unavailable" in failed["description"]
    assert "extract-123" in failed["description"]
    assert result["total"] == result["completed"] == 2


@pytest.mark.parametrize("failure", [requests.Timeout("read timed out"), requests.HTTPError("503 unavailable")])
def test_extract_transport_failure_preserves_existing_page_skip(fixture, failure):
    _, responses = fixture
    responses["search"]["results"] = [
        {"url": "https://example.test/failed", "content": ""},
        {"url": "https://example.test/ok", "content": "usable snippet"},
    ]
    responses["extract"] = failure
    result = final(crawl({"include_raw_content": True}))
    assert [page["source_url"] for page in result["web_info_list"]] == ["https://example.test/ok"]
    assert result["web_info_list"][0]["content"] == "usable snippet"
    assert result["total"] == result["completed"] == 1


def test_search_transport_failure_preserves_crawl_error(fixture):
    _, responses = fixture
    responses["search"] = requests.HTTPError("401 invalid key")
    with pytest.raises(ValueError, match="An error occurred: 401 invalid key"):
        crawl({})


def test_empty_search_keeps_completed_shape(fixture):
    result = final(crawl({}))
    assert result == {"status": "completed", "web_info_list": [], "total": 0, "completed": 0}


def test_extract_redirect_retains_content_for_the_single_requested_page(fixture):
    _, responses = fixture
    responses["search"]["results"] = [{"url": "https://example.test/old", "content": ""}]
    responses["extract"] = {"results": [{"url": "https://example.test/new", "raw_content": "Redirected content"}]}
    result = final(crawl({"include_raw_content": True}))
    assert result["web_info_list"][0]["content"] == "Redirected content"
    assert result["web_info_list"][0]["source_url"] == "https://example.test/old"

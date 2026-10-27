import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
import yaml
from dify_plugin.entities.tool import ToolParameter, ToolRuntime

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.tavily_search import TavilySearchTool
from tools.tavily_research import TavilyResearchTool
import tools.tavily_research as research_module


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr("socket.socket.connect", lambda *a, **k: pytest.fail("Unexpected network"))


@pytest.fixture
def transport(monkeypatch):
    calls = []
    response_body = {"results": [{"url": "https://example.test", "title": "Title", "content": "Snippet"}], "request_id": "search-id", "usage": {"credits": 1}}
    handler = SimpleNamespace(body=response_body, callback=None)

    def send(session, request, **kwargs):
        body = json.loads(request.body) if request.body else None
        calls.append((request, body, kwargs))
        status, payload = handler.callback(request, body) if handler.callback else (200, handler.body)
        response = requests.Response()
        response.status_code = status
        response._content = json.dumps(payload).encode()
        response.request = request
        response.headers["Content-Type"] = "application/json"
        return response

    monkeypatch.setattr(requests.Session, "send", send)
    return calls, handler


def invoke(cls, params, credentials=None):
    runtime = ToolRuntime(credentials={"tavily_api_key": "test-key"} if credentials is None else credentials, user_id=None, session_id=None)
    return list(cls(runtime=runtime, session=None).invoke(params.copy()))


def texts(messages):
    return "\n".join(m.message.text for m in messages if m.type.value == "text")


@pytest.mark.parametrize("depth", ["basic", "advanced", "fast", "ultra-fast"])
@pytest.mark.parametrize("chunks", [1, 3])
def test_chunks_depth_matrix(transport, depth, chunks):
    calls, _ = transport
    invoke(TavilySearchTool, {"query": "q", "search_depth": depth, "chunks_per_source": chunks})
    assert calls[-1][1].get("chunks_per_source") == (None if depth == "ultra-fast" else chunks)


@pytest.mark.parametrize("chunks", [0, 4, 1.5, True, "bad"])
def test_invalid_chunks_return_existing_error_message_without_http(transport, chunks):
    calls, _ = transport
    messages = invoke(TavilySearchTool, {"query": "q", "chunks_per_source": chunks})
    assert not calls
    assert "Error occurred while searching:" in texts(messages)


def test_defaults_and_full_json_output_preserved(transport):
    calls, response = transport
    messages = invoke(TavilySearchTool, {"query": "q"})
    body = calls[-1][1]
    assert body["max_results"] == 5
    assert body["search_depth"] == "basic"
    assert body["topic"] == "general"
    assert "chunks_per_source" not in body
    assert "include_domains_mode" not in body
    assert next(m.message.json_object for m in messages if m.type.value == "json") == response.body
    assert "Snippet" in texts(messages)
    assert calls[-1][0].headers["X-Client-Name"] == "dify"
    assert calls[-1][0].headers["X-Client-Source"] == "tavily-python"


@pytest.mark.parametrize("flag", [False, True])
def test_current_search_controls_reach_sdk_wire(transport, flag):
    calls, _ = transport
    invoke(TavilySearchTool, {"query": '"q"', "include_domains": "example.test", "include_domains_mode": "prefer", "language": "en", "filter_by_language": flag, "include_published_date": flag, "filter_by_published_date": flag, "safe_search": flag, "exact_match": flag, "max_results": 0})
    body = calls[-1][1]
    assert body["max_results"] == 0
    assert body["include_domains"] == ["example.test"]
    assert body["include_domains_mode"] == "prefer"
    assert body["language"] == "en"
    for name in ["filter_by_language", "include_published_date", "filter_by_published_date", "safe_search", "exact_match"]:
        assert body[name] is flag


@pytest.mark.parametrize("params", [
    {"include_domains_mode": "prefer"},
    {"include_domains": "example.test", "include_domains_mode": "invalid"},
    {"filter_by_language": True},
    {"filter_by_language": True, "language": "  "},
    {"search_depth": "fast", "safe_search": True},
    {"search_depth": "ultra-fast", "safe_search": True},
])
def test_new_cross_field_errors_use_existing_message_shape(transport, params):
    calls, _ = transport
    messages = invoke(TavilySearchTool, {"query": "q", **params})
    assert not calls
    assert "Error occurred while searching:" in texts(messages)


def test_yaml_schema_and_new_fields():
    data = yaml.safe_load((Path(__file__).resolve().parents[1] / "tools/tavily_search.yaml").read_text())
    params = {p["name"]: ToolParameter.model_validate(p) for p in data["parameters"]}
    expected = {"include_domains_mode", "language", "filter_by_language", "include_published_date", "filter_by_published_date", "safe_search", "exact_match"}
    assert expected <= params.keys()
    assert params["max_results"].default == 5
    assert params["max_results"].min == 1
    assert "basic" in params["chunks_per_source"].llm_description


@pytest.fixture
def clock(monkeypatch):
    now = [0.0]
    def sleep(seconds):
        assert seconds >= 0
        now[0] += seconds
    monkeypatch.setattr(research_module, "time", SimpleNamespace(time=lambda: now[0], monotonic=lambda: now[0], sleep=sleep))
    monkeypatch.setattr(TavilyResearchTool, "MAX_POLL_DURATION_SECONDS", 12, raising=False)
    return now


@pytest.mark.parametrize("status", ["pending", "in_progress", "unexpected"])
def test_research_nonterminal_deadline_retains_id_and_submits_once(transport, clock, status):
    calls, response = transport
    def handler(request, body):
        if request.method == "POST":
            return 200, {"request_id": "task-123", "status": "pending"}
        if len(calls) > 10:
            raise RuntimeError("test safety stop for unbounded loop")
        return 200, {"request_id": "task-123", "status": status}
    response.callback = handler
    output = invoke(TavilyResearchTool, {"input": "question", "model": "mini"})
    assert "timed out" in texts(output).lower()
    assert "task-123" in texts(output)
    assert clock[0] <= 12
    assert sum(c[0].method == "POST" for c in calls) == 1


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_research_terminal_result_and_existing_parameters_preserved(transport, clock, status):
    calls, response = transport
    result = {"request_id": "task-123", "status": status, "content": "Report", "sources": [{"url": "https://example.test", "title": "Title"}], "error": "reason"}
    response.callback = lambda req, body: (200, {"request_id": "task-123"}) if req.method == "POST" else (200, result)
    output = invoke(TavilyResearchTool, {"input": "question", "model": "mini", "citation_format": "apa"})
    assert next(m.message.json_object for m in output if m.type.value == "json") == result
    assert calls[0][1]["citation_format"] == "apa"
    assert not any(k in calls[0][1] for k in ["files", "output_schema", "output_length"])


def test_research_generator_close_stops_before_submission(transport):
    calls, _ = transport
    runtime = ToolRuntime(credentials={"tavily_api_key": "test-key"}, user_id=None, session_id=None)
    generator = TavilyResearchTool(runtime, None).invoke({"input": "question"})
    next(generator)
    generator.close()
    assert not calls


def test_research_interrupt_not_swallowed(transport, clock):
    _, response = transport
    def handler(request, body):
        if request.method == "POST":
            return 200, {"request_id": "task-123"}
        raise KeyboardInterrupt()
    response.callback = handler
    with pytest.raises(KeyboardInterrupt):
        invoke(TavilyResearchTool, {"input": "q"})


@pytest.mark.parametrize("params", [{"include_domains_mode": "not_specified"}, {"include_domains_mode": None}, {"language": "", "filter_by_language": False}, {"search_depth": "fast", "safe_search": False}])
def test_optional_and_false_controls_remain_valid(transport, params):
    calls, _ = transport
    messages = invoke(TavilySearchTool, {"query": "q", **params})
    assert len(calls) == 1
    assert any(m.type.value == "json" for m in messages)


def test_search_http_errors_keep_text_error_convention(transport):
    _, response = transport
    response.callback = lambda req, body: (400, {"detail": {"error": "Invalid search option"}})
    output = invoke(TavilySearchTool, {"query": "q"})
    assert "Error occurred while searching:" in texts(output)
    assert "Invalid search option" in texts(output)
    assert not any(m.type.value == "json" for m in output)


def test_general_search_publication_date_is_visible_when_requested(transport):
    _, response = transport
    response.body["results"][0]["published_date"] = "2026-10-01"
    messages = invoke(TavilySearchTool, {"query": "q", "include_published_date": True})
    assert "Published Date:** 2026-10-01" in texts(messages)


def test_research_close_after_creation_does_not_poll(transport):
    calls, response = transport
    response.body = {"request_id": "task-123", "status": "pending"}
    runtime = ToolRuntime(credentials={"tavily_api_key": "test-key"}, user_id=None, session_id=None)
    generator = TavilyResearchTool(runtime, None).invoke({"input": "question"})
    next(generator)  # Starting message; no API call yet.
    next(generator)  # Created message with the task ID.
    generator.close()
    assert len(calls) == 1
    assert calls[0][0].method == "POST"

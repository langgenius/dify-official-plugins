"""In-process tests for tools/searchapi (no pytest required).

These tests cover three reliability fixes shipped in this PR:

- Bug 1: missing `timeout=` on `requests.get` calls.
- Bug 2: `KeyError` when `searchapi_api_key` is missing from credentials.
- Bug 3 (google / google_news / google_jobs only): `_invoke()` falling through
  after invalid `hl` / `gl` yields.

They use only Python stdlib (`unittest.mock`) and tiny in-test stubs for
`requests`, `dify_plugin`, and `pydantic` so they can run in environments
where the plugin dependencies are not pre-installed.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

_HERE = Path(__file__).resolve().parent          # tests/
_PLUGIN_ROOT = _HERE.parent                       # tools/searchapi/
sys.path.insert(0, str(_PLUGIN_ROOT))             # so `tools.google` etc. resolve


# ---- Stub modules for optional/unavailable dependencies ---------------------

def _ensure_stub_modules() -> None:
    """Insert minimal stubs into sys.modules if a dep is not installed."""
    if "requests" not in sys.modules:
        requests_stub = types.ModuleType("requests")
        requests_stub.exceptions = types.SimpleNamespace(
            RequestException=type("RequestException", (Exception,), {})
        )

        def _default_get(*args, **kwargs):
            raise AssertionError(
                "requests.get was called in a test that did not patch it"
            )

        requests_stub.get = _default_get
        sys.modules["requests"] = requests_stub

    if "dify_plugin" not in sys.modules:
        dify_plugin_stub = types.ModuleType("dify_plugin")

        class _BaseTool:
            """Bare-minimum stand-in for dify_plugin.Tool."""

            def __init__(self):
                self.runtime = SimpleNamespace(credentials={})

            def create_text_message(self, text):
                return ("text", text)

            def create_json_message(self, json):
                return ("json", json)

            def create_link_message(self, link):
                return ("link", link)

        dify_plugin_stub.Tool = _BaseTool

        dify_plugin_entities_stub = types.ModuleType("dify_plugin.entities")
        tool_module_stub = types.ModuleType("dify_plugin.entities.tool")

        class _ToolInvokeMessage:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        tool_module_stub.ToolInvokeMessage = _ToolInvokeMessage

        dify_plugin_entities_stub.tool = tool_module_stub
        sys.modules["dify_plugin"] = dify_plugin_stub
        sys.modules["dify_plugin.entities"] = dify_plugin_entities_stub
        sys.modules["dify_plugin.entities.tool"] = tool_module_stub


_ensure_stub_modules()

# Force-fresh imports so we get the patched stubs above.
for _name in list(sys.modules):
    if _name.startswith("tools."):
        sys.modules.pop(_name, None)

# The searchapi plugin does not have a tools/ directory layout with __init__.py.
# Its tool files live directly under tools/searchapi/tools/, so we put that
# directory on sys.path (already done above) and import by file name.
from importlib import util as _importlib_util  # noqa: E402


def _load_module(file_name: str):
    path = _PLUGIN_ROOT / "tools" / file_name
    spec = _importlib_util.spec_from_file_location(f"searchapi.{file_name[:-3]}", path)
    mod = _importlib_util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


google = _load_module("google.py")
google_news = _load_module("google_news.py")
google_jobs = _load_module("google_jobs.py")
youtube_transcripts = _load_module("youtube_transcripts.py")


# ---- Local helpers ----------------------------------------------------------

class _FakeResponse:
    def __init__(self, payload=None, *, status_code=200):
        self._payload = payload if payload is not None else {
            "organic_results": [
                {
                    "title": "Example result",
                    "link": "https://example.com",
                    "snippet": "An example snippet.",
                }
            ]
        }
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def _make_tool(tool_cls, credentials, with_messages=True):
    """Build a bare tool instance bound to the given credentials dict."""
    tool = object.__new__(tool_cls)
    tool.runtime = SimpleNamespace(credentials=credentials)
    if with_messages:

        def _text(text):
            return ("text", text)

        def _json(json=None, **_kw):
            return ("json", json)

        def _link(link):
            return ("link", link)

        tool.create_text_message = _text
        tool.create_json_message = _json
        tool.create_link_message = _link
    return tool


def _flatten(messages):
    return list(messages)


# =============================================================================
# Bug 2: missing-credential guard
# =============================================================================

def test_google_missing_api_key_returns_message_and_no_http_call():
    tool = _make_tool(google.GoogleTool, credentials={})
    fake_get = mock.Mock(side_effect=AssertionError("requests.get must not be called"))
    with mock.patch.object(google.requests, "get", fake_get):
        messages = _flatten(tool._invoke({"query": "hello", "result_type": "text"}))
    assert len(messages) == 1
    assert messages[0][0] == "text"
    assert messages[0][1] == "SearchAPI API key is required."
    assert fake_get.call_count == 0


def test_google_empty_api_key_returns_message_and_no_http_call():
    tool = _make_tool(google.GoogleTool, credentials={"searchapi_api_key": ""})
    fake_get = mock.Mock(side_effect=AssertionError("requests.get must not be called"))
    with mock.patch.object(google.requests, "get", fake_get):
        messages = _flatten(tool._invoke({"query": "hello", "result_type": "text"}))
    assert len(messages) == 1
    assert messages[0][1] == "SearchAPI API key is required."
    assert fake_get.call_count == 0


def test_google_news_missing_api_key_returns_message_and_no_http_call():
    tool = _make_tool(google_news.GoogleNewsTool, credentials={})
    fake_get = mock.Mock(side_effect=AssertionError("requests.get must not be called"))
    with mock.patch.object(google_news.requests, "get", fake_get):
        messages = _flatten(tool._invoke({"query": "hello", "result_type": "text"}))
    assert messages[0][1] == "SearchAPI API key is required."
    assert fake_get.call_count == 0


def test_google_jobs_missing_api_key_returns_message_and_no_http_call():
    tool = _make_tool(google_jobs.GoogleJobsTool, credentials={})
    fake_get = mock.Mock(side_effect=AssertionError("requests.get must not be called"))
    with mock.patch.object(google_jobs.requests, "get", fake_get):
        messages = _flatten(tool._invoke({"query": "hello", "result_type": "text"}))
    assert messages[0][1] == "SearchAPI API key is required."
    assert fake_get.call_count == 0


def test_youtube_transcripts_missing_api_key_returns_message_and_no_http_call():
    tool = _make_tool(youtube_transcripts.YoutubeTranscriptsTool, credentials={})
    fake_get = mock.Mock(side_effect=AssertionError("requests.get must not be called"))
    with mock.patch.object(youtube_transcripts.requests, "get", fake_get):
        messages = _flatten(tool._invoke({"video_id": "abc123", "language": "en"}))
    assert messages[0][1] == "SearchAPI API key is required."
    assert fake_get.call_count == 0


# =============================================================================
# Bug 2 corollary: missing key did NOT raise KeyError pre-fix. Lock that in so
# any regression to bare-dict access surfaces here.
# =============================================================================

def test_google_missing_api_key_does_not_raise_keyerror():
    tool = _make_tool(google.GoogleTool, credentials={})
    fake_get = mock.Mock(side_effect=AssertionError("requests.get must not be called"))
    with mock.patch.object(google.requests, "get", fake_get):
        # The pre-fix behaviour was KeyError: 'searchapi_api_key'. The post-fix
        # behaviour yields a friendly text message. Anything else is a regression.
        messages = _flatten(tool._invoke({"query": "hello", "result_type": "text"}))
    assert messages[0] == ("text", "SearchAPI API key is required.")


# =============================================================================
# Bug 3: invoke fall-through on invalid hl / gl (google / google_news / google_jobs)
# =============================================================================

def test_google_invalid_hl_returns_message_and_no_http_call():
    tool = _make_tool(google.GoogleTool, credentials={"searchapi_api_key": "secret"})
    fake_get = mock.Mock(side_effect=AssertionError("requests.get must not be called"))
    with mock.patch.object(google.requests, "get", fake_get):
        messages = _flatten(
            tool._invoke({"query": "hello", "result_type": "text", "hl": "zzzz", "gl": "us"})
        )
    assert messages[0][0] == "text"
    assert "Invalid 'hl' parameter" in messages[0][1]
    assert fake_get.call_count == 0


def test_google_invalid_gl_returns_message_and_no_http_call():
    tool = _make_tool(google.GoogleTool, credentials={"searchapi_api_key": "secret"})
    fake_get = mock.Mock(side_effect=AssertionError("requests.get must not be called"))
    with mock.patch.object(google.requests, "get", fake_get):
        messages = _flatten(
            tool._invoke({"query": "hello", "result_type": "text", "hl": "en", "gl": "12"})
        )
    assert "Invalid 'gl' parameter" in messages[0][1]
    assert fake_get.call_count == 0


def test_google_news_invalid_hl_returns_message_and_no_http_call():
    tool = _make_tool(google_news.GoogleNewsTool, credentials={"searchapi_api_key": "secret"})
    fake_get = mock.Mock(side_effect=AssertionError("requests.get must not be called"))
    with mock.patch.object(google_news.requests, "get", fake_get):
        messages = _flatten(
            tool._invoke({"query": "hello", "result_type": "text", "hl": "12"})
        )
    assert "Invalid 'hl' parameter" in messages[0][1]
    assert fake_get.call_count == 0


def test_google_jobs_invalid_gl_returns_message_and_no_http_call():
    tool = _make_tool(google_jobs.GoogleJobsTool, credentials={"searchapi_api_key": "secret"})
    fake_get = mock.Mock(side_effect=AssertionError("requests.get must not be called"))
    with mock.patch.object(google_jobs.requests, "get", fake_get):
        messages = _flatten(
            tool._invoke({"query": "hello", "result_type": "text", "gl": "12"})
        )
    assert "Invalid 'gl' parameter" in messages[0][1]
    assert fake_get.call_count == 0


# =============================================================================
# Bug 1: requests.get forwards a 10s timeout on every call site.
# =============================================================================

def test_google_requests_get_uses_10s_timeout_on_results_call():
    tool = _make_tool(google.GoogleTool, credentials={"searchapi_api_key": "secret"})
    fake_response = _FakeResponse()
    fake_get = mock.Mock(return_value=fake_response)
    with mock.patch.object(google.requests, "get", fake_get):
        _flatten(tool._invoke({"query": "hello", "result_type": "text"}))
    assert fake_get.call_count == 1
    _, kwargs = fake_get.call_args
    assert kwargs.get("timeout") == 10, f"expected timeout=10 kwarg, got {kwargs!r}"


def test_google_news_requests_get_uses_10s_timeout_on_results_call():
    tool = _make_tool(google_news.GoogleNewsTool, credentials={"searchapi_api_key": "secret"})
    fake_response = _FakeResponse()
    fake_get = mock.Mock(return_value=fake_response)
    with mock.patch.object(google_news.requests, "get", fake_get):
        _flatten(tool._invoke({"query": "hello", "result_type": "text"}))
    _, kwargs = fake_get.call_args
    assert kwargs.get("timeout") == 10, f"expected timeout=10 kwarg, got {kwargs!r}"


def test_google_jobs_requests_get_uses_10s_timeout_on_results_call():
    tool = _make_tool(google_jobs.GoogleJobsTool, credentials={"searchapi_api_key": "secret"})
    fake_response = _FakeResponse()
    fake_get = mock.Mock(return_value=fake_response)
    with mock.patch.object(google_jobs.requests, "get", fake_get):
        _flatten(tool._invoke({"query": "hello", "result_type": "text"}))
    _, kwargs = fake_get.call_args
    assert kwargs.get("timeout") == 10, f"expected timeout=10 kwarg, got {kwargs!r}"


def test_youtube_transcripts_requests_get_uses_10s_timeout_on_results_call():
    tool = _make_tool(youtube_transcripts.YoutubeTranscriptsTool, credentials={"searchapi_api_key": "secret"})
    fake_response = _FakeResponse(payload={"transcripts": [{"text": "hi"}]})
    fake_get = mock.Mock(return_value=fake_response)
    with mock.patch.object(youtube_transcripts.requests, "get", fake_get):
        _flatten(tool._invoke({"video_id": "abc123", "language": "en"}))
    _, kwargs = fake_get.call_args
    assert kwargs.get("timeout") == 10, f"expected timeout=10 kwarg, got {kwargs!r}"


# =============================================================================
# Happy-path smoke: a valid invocation still produces text and link messages.
# =============================================================================

def test_google_happy_path_yields_text_and_link_messages():
    tool = _make_tool(google.GoogleTool, credentials={"searchapi_api_key": "secret"})
    fake_response = _FakeResponse(
        payload={
            "organic_results": [
                {"title": "T", "link": "https://x", "snippet": "S"},
            ]
        }
    )
    fake_get = mock.Mock(return_value=fake_response)
    with mock.patch.object(google.requests, "get", fake_get):
        messages = _flatten(
            tool._invoke({"query": "hello", "result_type": "text"})
        )
    kinds = [m[0] for m in messages]
    assert "text" in kinds
    assert "link" in kinds


# =============================================================================
# Network failure surfaces as a friendly message, not a stack trace.
# =============================================================================

def test_google_request_exception_yields_friendly_message():
    tool = _make_tool(google.GoogleTool, credentials={"searchapi_api_key": "secret"})
    fake_get = mock.Mock(side_effect=google.requests.exceptions.RequestException("boom"))
    with mock.patch.object(google.requests, "get", fake_get):
        messages = _flatten(
            tool._invoke({"query": "hello", "result_type": "text"})
        )
    assert any(
        m[0] == "text" and "boom" in m[1] for m in messages
    ), f"expected friendly error message containing 'boom', got {messages!r}"

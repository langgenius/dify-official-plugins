"""In-process tests for tools/serper (pytest-shaped).

These tests cover two reliability fixes shipped in this PR:

- Bug 1: missing `timeout=` on `requests.get` calls.
- Bug 2: `KeyError` when `serperapi_api_key` is missing from credentials.

`serper_search.py` does not take `hl` / `gl` user input (the values are hardcoded
to "us" / "en"), so the third bug from PR #3456 (invoke fall-through on invalid
hl / gl) does not apply.

Run with: python3 -m pytest tests/test_serper.py -v

They use `unittest.mock` and tiny in-test stubs for `requests` and `dify_plugin`
so they can run in environments where the plugin dependencies are not installed.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

_HERE = Path(__file__).resolve().parent          # tests/
_PLUGIN_ROOT = _HERE.parent                       # tools/serper/
sys.path.insert(0, str(_PLUGIN_ROOT))             # so `tools.serper_search` works


# ---- Stub modules ----------------------------------------------------------

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
    if _name.startswith("tools.serper"):
        sys.modules.pop(_name, None)

from importlib import util as _importlib_util  # noqa: E402


def _load_module(file_name: str):
    path = _PLUGIN_ROOT / "tools" / file_name
    spec = _importlib_util.spec_from_file_location(f"serper.{file_name[:-3]}", path)
    mod = _importlib_util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


serper = _load_module("serper_search.py")


# ---- Helpers ---------------------------------------------------------------

class _FakeResponse:
    def __init__(self, payload=None, *, status_code=200):
        self._payload = payload if payload is not None else {
            "knowledgeGraph": {"title": "Example", "description": "An example."},
            "organic": [{"title": "T", "link": "https://x", "snippet": "S"}],
        }
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def _make_tool(credentials):
    tool = object.__new__(serper.SerperSearchTool)

    def _text(text):
        return ("text", text)

    def _json(json=None, **_kw):
        return ("json", json)

    tool.create_text_message = _text
    tool.create_json_message = _json
    tool.runtime = SimpleNamespace(credentials=credentials)
    return tool


def _flatten(messages):
    return list(messages)


# =============================================================================
# Bug 2: missing-credential guard
# =============================================================================

def test_serper_missing_api_key_returns_message_and_no_http_call():
    tool = _make_tool(credentials={})
    fake_get = mock.Mock(side_effect=AssertionError("requests.get must not be called"))
    with mock.patch.object(serper.requests, "get", fake_get):
        messages = _flatten(tool._invoke({"query": "hello"}))
    assert len(messages) == 1
    assert messages[0][0] == "text"
    assert messages[0][1] == "Serper.dev API key is required."
    assert fake_get.call_count == 0


def test_serper_empty_api_key_returns_message_and_no_http_call():
    tool = _make_tool(credentials={"serperapi_api_key": ""})
    fake_get = mock.Mock(side_effect=AssertionError("requests.get must not be called"))
    with mock.patch.object(serper.requests, "get", fake_get):
        messages = _flatten(tool._invoke({"query": "hello"}))
    assert messages[0][1] == "Serper.dev API key is required."
    assert fake_get.call_count == 0


def test_serper_missing_api_key_does_not_raise_keyerror():
    """Lock the post-fix contract: missing key never raises KeyError."""
    tool = _make_tool(credentials={})
    fake_get = mock.Mock(side_effect=AssertionError("requests.get must not be called"))
    with mock.patch.object(serper.requests, "get", fake_get):
        messages = _flatten(tool._invoke({"query": "hello"}))
    assert messages[0] == ("text", "Serper.dev API key is required.")


# =============================================================================
# Bug 1: requests.get forwards a 10s timeout.
# =============================================================================

def test_serper_requests_get_uses_10s_timeout():
    tool = _make_tool(credentials={"serperapi_api_key": "secret"})
    fake_response = _FakeResponse()
    fake_get = mock.Mock(return_value=fake_response)
    with mock.patch.object(serper.requests, "get", fake_get):
        _flatten(tool._invoke({"query": "hello"}))
    assert fake_get.call_count == 1
    _, kwargs = fake_get.call_args
    assert kwargs.get("timeout") == 10, f"expected timeout=10 kwarg, got {kwargs!r}"


# =============================================================================
# Happy-path smoke
# =============================================================================

def test_serper_happy_path_yields_json_message():
    tool = _make_tool(credentials={"serperapi_api_key": "secret"})
    fake_response = _FakeResponse()
    fake_get = mock.Mock(return_value=fake_response)
    with mock.patch.object(serper.requests, "get", fake_get):
        messages = _flatten(tool._invoke({"query": "hello"}))
    assert any(m[0] == "json" for m in messages)


# =============================================================================
# Network failure surfaces as a friendly message, not a stack trace.
# =============================================================================

def test_serper_request_exception_yields_friendly_message():
    tool = _make_tool(credentials={"serperapi_api_key": "secret"})
    fake_get = mock.Mock(side_effect=serper.requests.exceptions.RequestException("boom"))
    with mock.patch.object(serper.requests, "get", fake_get):
        messages = _flatten(tool._invoke({"query": "hello"}))
    assert any(
        m[0] == "text" and "boom" in m[1] for m in messages
    ), f"expected friendly error message containing 'boom', got {messages!r}"

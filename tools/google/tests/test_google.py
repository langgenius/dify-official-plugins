"""In-process tests for tools/google (no pytest required).

These tests cover three reliability fixes shipped in this PR:

- Bug 1: missing `timeout=` on `requests.get` calls.
- Bug 2: `_invoke()` falling through after invalid `hl` / `gl` yields.
- Bug 3: `KeyError` when `serpapi_api_key` is missing from credentials.

They use only Python stdlib (`unittest.mock`) and tiny in-test stubs for
`requests`, `dify_plugin`, `loguru`, and `pydantic` so they can run in
environments where the plugin dependencies are not pre-installed.
"""

from __future__ import annotations

import importlib
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

# Resolve paths so `tools.google_search`, `tools.utils`, `dify_plugin`, etc.
# resolve identically to how they resolve at plugin runtime.
_HERE = Path(__file__).resolve().parent          # tests/
_PLUGIN_ROOT = _HERE.parent                       # tools/google/
_REPO_ROOT = _PLUGIN_ROOT.parent.parent.parent     # repo root (dify-official-plugins)
sys.path.insert(0, str(_REPO_ROOT))               # so `tools.utils` works
sys.path.insert(0, str(_PLUGIN_ROOT))             # so `tools.google_search` works


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

    if "loguru" not in sys.modules:
        loguru_stub = types.ModuleType("loguru")
        loguru_stub.logger = types.SimpleNamespace(
            warning=lambda *a, **kw: None,
            info=lambda *a, **kw: None,
            error=lambda *a, **kw: None,
            debug=lambda *a, **kw: None,
        )
        sys.modules["loguru"] = loguru_stub

    if "pydantic" not in sys.modules:
        pydantic_stub = types.ModuleType("pydantic")

        class _BaseModel:
            """Minimal stand-in: stores the kwargs passed to __init__."""

            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

            def model_dump(self, mode=None, **_):
                # Capture all attributes set by __init__ (and model_post_init).
                payload = {}
                for k, v in vars(self).items():
                    if k.startswith("_"):
                        continue
                    payload[k] = v
                return payload

        pydantic_stub.BaseModel = _BaseModel

        def _field(*_args, **_kwargs):
            return None

        pydantic_stub.Field = _field
        sys.modules["pydantic"] = pydantic_stub

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
    if _name.startswith("tools.google") or _name in {"tools.utils"}:
        sys.modules.pop(_name, None)

from tools import google_search, google_image_search  # noqa: E402


# ---- Local helpers ----------------------------------------------------------

class _FakeResponse:
    def __init__(self, payload=None, *, status_code=200, raise_status=False):
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
        self._raise_status = raise_status

    def raise_for_status(self):
        if self._raise_status or self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _MessageToolMixin:
    """Mixin so `self.create_text_message(...)` returns a captureable tuple."""

    def create_text_message(self, text):
        return ("text", text)

    def create_json_message(self, json=None, **kwargs):
        return ("json", json)


def _search_tool(credentials):
    tool = object.__new__(google_search.GoogleSearchTool)
    tool.runtime = SimpleNamespace(credentials=credentials)
    for name in ("create_text_message", "create_json_message"):
        setattr(
            tool,
            name,
            getattr(_MessageToolMixin, name).__get__(tool, type(tool)),
        )
    return tool


def _image_tool(credentials):
    tool = object.__new__(google_image_search.GoogleImageSearchTool)
    tool.runtime = SimpleNamespace(credentials=credentials)
    for name in ("create_text_message", "create_json_message"):
        setattr(
            tool,
            name,
            getattr(_MessageToolMixin, name).__get__(tool, type(tool)),
        )
    return tool


def _flatten(messages):
    return list(messages)


# ---- Bug 3: missing-credential guard ----------------------------------------

def test_google_search_invoke_missing_api_key_returns_message_and_no_http_call():
    tool = _search_tool(credentials={})  # no serpapi_api_key at all
    fake_get = mock.Mock(side_effect=AssertionError("requests.get must not be called"))
    with mock.patch.object(google_search.requests, "get", fake_get):
        messages = _flatten(tool._invoke({"query": "hello"}))

    assert len(messages) == 1
    assert messages[0][0] == "text"
    assert messages[0][1] == "SerpAPI API key is required."
    assert fake_get.call_count == 0


def test_google_image_search_invoke_missing_api_key_returns_message_and_no_http_call():
    tool = _image_tool(credentials={"serpapi_api_key": ""})  # empty string is missing
    fake_get = mock.Mock(side_effect=AssertionError("requests.get must not be called"))
    with mock.patch.object(google_image_search.requests, "get", fake_get):
        messages = _flatten(tool._invoke({"query": "cats"}))

    assert len(messages) == 1
    assert messages[0][0] == "text"
    assert messages[0][1] == "SerpAPI API key is required."
    assert fake_get.call_count == 0


# ---- Bug 2: invoke fall-through on invalid hl / gl ---------------------------

def test_google_image_search_invoke_invalid_hl_returns_message_and_no_http_call():
    tool = _image_tool(credentials={"serpapi_api_key": "secret-key"})
    fake_get = mock.Mock(side_effect=AssertionError("requests.get must not be called"))
    with mock.patch.object(google_image_search.requests, "get", fake_get):
        messages = _flatten(tool._invoke({"query": "puppies", "hl": "zz", "gl": "us"}))

    assert len(messages) == 1
    assert messages[0][0] == "text"
    assert "Invalid 'hl' parameter: zz" in messages[0][1]
    assert fake_get.call_count == 0


def test_google_image_search_invoke_invalid_gl_returns_message_and_no_http_call():
    tool = _image_tool(credentials={"serpapi_api_key": "secret-key"})
    fake_get = mock.Mock(side_effect=AssertionError("requests.get must not be called"))
    with mock.patch.object(google_image_search.requests, "get", fake_get):
        messages = _flatten(tool._invoke({"query": "puppies", "hl": "en", "gl": "zz"}))

    assert len(messages) == 1
    assert messages[0][0] == "text"
    assert "Invalid 'gl' parameter: zz" in messages[0][1]
    assert fake_get.call_count == 0


# ---- Happy path: successful invocation --------------------------------------

def test_google_image_search_invoke_success_yields_results():
    tool = _image_tool(credentials={"serpapi_api_key": "secret-key"})

    response_payload = {
        "images_results": [
            {
                "title": "Sample image",
                "original": "https://example.com/img.png",
                "thumbnail": "https://example.com/thumb.png",
                "link": "https://example.com/page",
                "original_height": "600",
                "original_width": "800",
                "source": "example.com",
            }
        ]
    }
    fake_response = _FakeResponse(payload=response_payload)

    def fake_get(url, params=None, timeout=None, **kwargs):
        return fake_response

    with mock.patch.object(google_image_search.requests, "get", fake_get):
        messages = _flatten(tool._invoke({"query": "kittens", "hl": "en", "gl": "us"}))

    # Expect a leading text message with markdown, plus one JSON message per image.
    kinds = [m[0] for m in messages]
    assert kinds[0] == "text"
    assert "https://example.com/img.png" in messages[0][1]
    json_messages = [m for m in messages if m[0] == "json"]
    assert len(json_messages) == 1
    assert json_messages[0][1]["image"] == "https://example.com/img.png"
    assert json_messages[0][1]["extension"] == ".png"


def test_google_search_invoke_success_yields_results():
    tool = _search_tool(credentials={"serpapi_api_key": "secret-key"})
    response_payload = {
        "organic_results": [
            {
                "title": "Example result",
                "link": "https://example.com",
                "snippet": "An example snippet.",
            }
        ]
    }
    fake_response = _FakeResponse(payload=response_payload)

    def fake_get(url, params=None, timeout=None, **kwargs):
        return fake_response

    with mock.patch.object(google_search.requests, "get", fake_get):
        messages = _flatten(
            tool._invoke({"query": "hello world", "hl": "en", "gl": "us"})
        )

    # Search tool emits a single JSON message for non-agent use.
    json_messages = [m for m in messages if m[0] == "json"]
    assert len(json_messages) == 1
    assert json_messages[0][1]["organic_results"][0]["title"] == "Example result"


# ---- Bug 1: timeout kwarg is always passed ----------------------------------

def test_requests_get_called_with_timeout_10():
    """Both call sites must pass `timeout=10` to `requests.get`."""

    captured: list[dict] = []

    def fake_search_get(url, params=None, timeout=None, **kwargs):
        captured.append({"tool": "search", "timeout": timeout, "params": params})
        return _FakeResponse(
            payload={
                "organic_results": [
                    {
                        "title": "Result",
                        "link": "https://example.com",
                        "snippet": "snippet",
                    }
                ]
            }
        )

    def fake_image_get(url, params=None, timeout=None, **kwargs):
        captured.append({"tool": "image", "timeout": timeout, "params": params})
        return _FakeResponse(payload={"images_results": []})

    search_tool = _search_tool(credentials={"serpapi_api_key": "secret-key"})
    image_tool = _image_tool(credentials={"serpapi_api_key": "secret-key"})

    # The two `requests.get` call sites share the same module-level `requests`
    # import, so the patches cannot be active simultaneously without one
    # shadowing the other. Exercise them in two separate with-blocks.
    with mock.patch.object(google_search.requests, "get", fake_search_get):
        _flatten(search_tool._invoke({"query": "q1", "hl": "en", "gl": "us"}))

    with mock.patch.object(google_image_search.requests, "get", fake_image_get):
        _flatten(image_tool._invoke({"query": "q2", "hl": "en", "gl": "us"}))

    assert len(captured) == 2, captured
    for entry in captured:
        assert entry["timeout"] == 10, entry
    # Confirm both tools actually invoked requests.get.
    kinds = sorted(entry["tool"] for entry in captured)
    assert kinds == ["image", "search"]


def _main() -> int:
    """Run all `test_*` functions in this module and return 0 on success."""
    import traceback

    failures: list[tuple[str, str]] = []
    for name in sorted(n for n in dir(sys.modules[__name__]) if n.startswith("test_") and callable(getattr(sys.modules[__name__], n))):
        fn = getattr(sys.modules[__name__], name)
        try:
            fn()
        except Exception:  # noqa: BLE001
            failures.append((name, traceback.format_exc()))

    if failures:
        for name, tb in failures:
            print(f"FAIL: {name}\n{tb}")
        print(f"\n{len(failures)} failure(s)")
        return 1

    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(_main())

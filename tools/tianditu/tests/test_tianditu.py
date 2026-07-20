"""In-process tests for tools/tianditu (no pytest required).

These tests cover two reliability fixes shipped in this PR:

- Bug 1: missing `timeout=` on `requests.get` calls.
- Bug 2: `KeyError` when `tianditu_api_key` is missing from credentials.

`tianditu` does not take user-supplied `hl` / `gl` (the geocoder API takes a
`keyWord` and an optional `region` already from upstream, not through us),
so the third bug from PR #3456 (invoke fall-through on invalid hl/gl)
does not apply.

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
_PLUGIN_ROOT = _HERE.parent                       # tools/tianditu/
sys.path.insert(0, str(_PLUGIN_ROOT))             # so `tools.geocoder` etc. resolve


# ---- Stub modules ----------------------------------------------------------

def _ensure_stub_modules() -> None:
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
            def __init__(self):
                self.runtime = SimpleNamespace(credentials={})

            def create_text_message(self, text):
                return ("text", text)

            def create_json_message(self, json):
                return ("json", json)

            def create_blob_message(self, blob, meta=None):
                return ("blob", blob, meta)

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
    if _name.startswith("tools.tianditu") or _name.startswith("tools.geocoder") \
            or _name.startswith("tools.staticmap") or _name.startswith("tools.poisearch"):
        sys.modules.pop(_name, None)

from importlib import util as _importlib_util  # noqa: E402


def _load_module(file_name: str):
    path = _PLUGIN_ROOT / "tools" / file_name
    spec = _importlib_util.spec_from_file_location(f"tianditu.{file_name[:-3]}", path)
    mod = _importlib_util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


geocoder = _load_module("geocoder.py")
staticmap = _load_module("staticmap.py")
poisearch = _load_module("poisearch.py")


# ---- Helpers ---------------------------------------------------------------

class _FakeResponse:
    def __init__(self, payload=None, *, raw_bytes=b"\x89PNG\r\n"):
        if payload is not None:
            self._payload = payload
        else:
            self._payload = {
                "status": "0",
                "message": "ok",
                "location": {"lon": 116.404, "lat": 39.915},
            }
        self._raw_bytes = raw_bytes
        self.calls = 0  # some files make multiple requests.get calls

    def json(self):
        self.calls += 1
        return self._payload

    @property
    def content(self):
        return self._raw_bytes


def _make_tool(tool_cls, credentials):
    tool = object.__new__(tool_cls)

    def _text(text):
        return ("text", text)

    def _json(json=None, **_kw):
        return ("json", json)

    def _blob(blob, meta=None):
        return ("blob", blob, meta)

    tool.create_text_message = _text
    tool.create_json_message = _json
    tool.create_blob_message = _blob
    tool.runtime = SimpleNamespace(credentials=credentials)
    return tool


def _flatten(messages):
    return list(messages)


# =============================================================================
# Bug 2: missing-credential guard
# =============================================================================

def test_geocoder_missing_api_key_returns_message_and_no_http_call():
    tool = _make_tool(geocoder.GeocoderTool, credentials={})
    fake_get = mock.Mock(side_effect=AssertionError("requests.get must not be called"))
    with mock.patch.object(geocoder.requests, "get", fake_get):
        messages = _flatten(tool._invoke({"keyword": "Beijing"}))
    assert len(messages) == 1
    assert messages[0][0] == "text"
    assert messages[0][1] == "Tianditu API key is required."
    assert fake_get.call_count == 0


def test_geocoder_empty_api_key_returns_message_and_no_http_call():
    tool = _make_tool(geocoder.GeocoderTool, credentials={"tianditu_api_key": ""})
    fake_get = mock.Mock(side_effect=AssertionError("requests.get must not be called"))
    with mock.patch.object(geocoder.requests, "get", fake_get):
        messages = _flatten(tool._invoke({"keyword": "Beijing"}))
    assert messages[0][1] == "Tianditu API key is required."
    assert fake_get.call_count == 0


def test_staticmap_missing_api_key_returns_message_and_no_http_call():
    tool = _make_tool(staticmap.PoiSearchTool, credentials={})
    fake_get = mock.Mock(side_effect=AssertionError("requests.get must not be called"))
    with mock.patch.object(staticmap.requests, "get", fake_get):
        messages = _flatten(tool._invoke({"keyword": "Beijing"}))
    assert messages[0][1] == "Tianditu API key is required."
    assert fake_get.call_count == 0


def test_poisearch_missing_api_key_returns_message_and_no_http_call():
    tool = _make_tool(poisearch.PoiSearchTool, credentials={})
    fake_get = mock.Mock(side_effect=AssertionError("requests.get must not be called"))
    with mock.patch.object(poisearch.requests, "get", fake_get):
        messages = _flatten(tool._invoke({"keyword": "Beijing", "baseAddress": "Beijing"}))
    assert messages[0][1] == "Tianditu API key is required."
    assert fake_get.call_count == 0


# =============================================================================
# Bug 2 corollary: missing key did NOT raise KeyError pre-fix.
# =============================================================================

def test_geocoder_missing_api_key_does_not_raise_keyerror():
    tool = _make_tool(geocoder.GeocoderTool, credentials={})
    fake_get = mock.Mock(side_effect=AssertionError("requests.get must not be called"))
    with mock.patch.object(geocoder.requests, "get", fake_get):
        messages = _flatten(tool._invoke({"keyword": "Beijing"}))
    assert messages[0] == ("text", "Tianditu API key is required.")


# =============================================================================
# Bug 1: requests.get forwards a 10s timeout on every call.
# =============================================================================

def test_geocoder_requests_get_uses_10s_timeout():
    tool = _make_tool(geocoder.GeocoderTool, credentials={"tianditu_api_key": "secret"})
    fake_response = _FakeResponse(payload={"status": "0", "message": "ok"})
    fake_get = mock.Mock(return_value=fake_response)
    with mock.patch.object(geocoder.requests, "get", fake_get):
        _flatten(tool._invoke({"keyword": "Beijing"}))
    assert fake_get.call_count == 1
    _, kwargs = fake_get.call_args
    assert kwargs.get("timeout") == 10, f"expected timeout=10 kwarg, got {kwargs!r}"


def test_staticmap_requests_get_uses_10s_timeout_on_every_call():
    tool = _make_tool(staticmap.PoiSearchTool, credentials={"tianditu_api_key": "secret"})
    fake_response = _FakeResponse()
    fake_get = mock.Mock(return_value=fake_response)
    with mock.patch.object(staticmap.requests, "get", fake_get):
        _flatten(tool._invoke({"keyword": "Beijing"}))
    # staticmap makes 2 calls: geocoder look-up + static image fetch.
    assert fake_get.call_count == 2
    for call in fake_get.call_args_list:
        _, kwargs = call
        assert kwargs.get("timeout") == 10, f"expected timeout=10 kwarg, got {kwargs!r}"


def test_poisearch_requests_get_uses_10s_timeout_on_every_call():
    tool = _make_tool(poisearch.PoiSearchTool, credentials={"tianditu_api_key": "secret"})
    fake_response = _FakeResponse()
    fake_get = mock.Mock(return_value=fake_response)
    with mock.patch.object(poisearch.requests, "get", fake_get):
        _flatten(tool._invoke({"keyword": "Beijing", "baseAddress": "Beijing"}))
    # poisearch makes 2 calls: geocoder look-up + v2/search
    assert fake_get.call_count == 2
    for call in fake_get.call_args_list:
        _, kwargs = call
        assert kwargs.get("timeout") == 10, f"expected timeout=10 kwarg, got {kwargs!r}"


# =============================================================================
# Happy-path smoke
# =============================================================================

def test_geocoder_happy_path_yields_json_message():
    tool = _make_tool(geocoder.GeocoderTool, credentials={"tianditu_api_key": "secret"})
    fake_response = _FakeResponse()
    fake_get = mock.Mock(return_value=fake_response)
    with mock.patch.object(geocoder.requests, "get", fake_get):
        messages = _flatten(tool._invoke({"keyword": "Beijing"}))
    assert any(m[0] == "json" for m in messages)


def test_staticmap_happy_path_yields_blob_message():
    tool = _make_tool(staticmap.PoiSearchTool, credentials={"tianditu_api_key": "secret"})
    fake_response = _FakeResponse()
    fake_get = mock.Mock(return_value=fake_response)
    with mock.patch.object(staticmap.requests, "get", fake_get):
        messages = _flatten(tool._invoke({"keyword": "Beijing"}))
    assert any(m[0] == "blob" for m in messages)


# =============================================================================
# Network failure surfaces as a friendly message, not a stack trace.
# =============================================================================

def test_geocoder_request_exception_yields_friendly_message():
    tool = _make_tool(geocoder.GeocoderTool, credentials={"tianditu_api_key": "secret"})
    fake_get = mock.Mock(side_effect=geocoder.requests.exceptions.RequestException("boom"))
    with mock.patch.object(geocoder.requests, "get", fake_get):
        messages = _flatten(tool._invoke({"keyword": "Beijing"}))
    assert any(
        m[0] == "text" and "boom" in m[1] for m in messages
    ), f"expected friendly error message containing 'boom', got {messages!r}"

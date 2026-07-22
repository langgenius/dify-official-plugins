"""In-process tests for tools/brave (pytest-shaped)."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

_HERE = Path(__file__).resolve().parent
_PLUGIN_ROOT = _HERE.parent
sys.path.insert(0, str(_PLUGIN_ROOT))


def _ensure_stub_modules() -> None:
    if "requests" not in sys.modules:
        requests_stub = types.ModuleType("requests")
        requests_stub.exceptions = types.SimpleNamespace(
            RequestException=type("RequestException", (Exception,), {})
        )
        requests_stub.PreparedRequest = type(
            "PreparedRequest",
            (),
            {"prepare_url": lambda self, url, params: setattr(self, "url", url + "?q=test") or None},
        )
        requests_stub.get = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("requests.get must be patched")
        )
        sys.modules["requests"] = requests_stub

    if "pydantic" not in sys.modules:
        pydantic_stub = types.ModuleType("pydantic")

        class _BaseModel:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        pydantic_stub.BaseModel = _BaseModel
        pydantic_stub.Field = lambda *a, **k: None
        sys.modules["pydantic"] = pydantic_stub

    if "dify_plugin" not in sys.modules:
        dify_plugin_stub = types.ModuleType("dify_plugin")

        class _BaseTool:
            def create_text_message(self, text):
                return ("text", text)

        dify_plugin_stub.Tool = _BaseTool
        entities = types.ModuleType("dify_plugin.entities")
        tool_mod = types.ModuleType("dify_plugin.entities.tool")
        tool_mod.ToolInvokeMessage = type("ToolInvokeMessage", (), {})
        entities.tool = tool_mod
        sys.modules["dify_plugin"] = dify_plugin_stub
        sys.modules["dify_plugin.entities"] = entities
        sys.modules["dify_plugin.entities.tool"] = tool_mod


_ensure_stub_modules()
for _name in list(sys.modules):
    if _name.startswith("tools.brave") or _name == "brave_search":
        sys.modules.pop(_name, None)

from importlib import util as _importlib_util  # noqa: E402

spec = _importlib_util.spec_from_file_location(
    "brave_search", _PLUGIN_ROOT / "tools" / "brave_search.py"
)
brave_search = _importlib_util.module_from_spec(spec)
sys.modules[spec.name] = brave_search
spec.loader.exec_module(brave_search)


class _FakeResponse:
    ok = True

    def json(self):
        return {"web": {"results": [{"title": "T", "url": "https://x", "description": "S"}]}}


def _make_tool(credentials):
    tool = object.__new__(brave_search.BraveSearchTool)
    tool.runtime = SimpleNamespace(credentials=credentials)
    tool.create_text_message = lambda text: ("text", text)
    return tool


def test_brave_missing_api_key_no_http():
    tool = _make_tool({})
    fake_get = mock.Mock(side_effect=AssertionError("no http"))
    with mock.patch.object(brave_search.requests, "get", fake_get):
        msgs = list(tool._invoke({"query": "hello"}))
    assert msgs[0][1] == "Brave Search API key is required."
    assert fake_get.call_count == 0


def test_brave_requests_get_uses_timeout():
    tool = _make_tool({"brave_search_api_key": "secret"})
    fake_get = mock.Mock(return_value=_FakeResponse())
    with mock.patch.object(brave_search.requests, "get", fake_get):
        list(tool._invoke({"query": "hello"}))
    assert fake_get.call_args.kwargs.get("timeout") == 10


def test_brave_happy_path():
    tool = _make_tool({"brave_search_api_key": "secret"})
    fake_get = mock.Mock(return_value=_FakeResponse())
    with mock.patch.object(brave_search.requests, "get", fake_get):
        msgs = list(tool._invoke({"query": "hello"}))
    assert any(m[0] == "text" and "T" in m[1] for m in msgs)


def test_brave_request_exception():
    tool = _make_tool({"brave_search_api_key": "secret"})
    fake_get = mock.Mock(side_effect=brave_search.requests.exceptions.RequestException("timeout"))
    with mock.patch.object(brave_search.requests, "get", fake_get):
        msgs = list(tool._invoke({"query": "hello"}))
    assert any(m[0] == "text" and "timeout" in m[1] for m in msgs)

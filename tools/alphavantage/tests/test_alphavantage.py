"""In-process tests for tools/alphavantage (pytest-shaped)."""

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
        requests_stub.get = lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("requests.get must be patched")
        )
        sys.modules["requests"] = requests_stub

    if "dify_plugin" not in sys.modules:
        dify_plugin_stub = types.ModuleType("dify_plugin")

        class _BaseTool:
            def create_text_message(self, text):
                return ("text", text)

            def create_json_message(self, json):
                return ("json", json)

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
    if _name.startswith("query_stock"):
        sys.modules.pop(_name, None)

from importlib import util as _importlib_util  # noqa: E402

spec = _importlib_util.spec_from_file_location(
    "query_stock", _PLUGIN_ROOT / "tools" / "query_stock.py"
)
query_stock = _importlib_util.module_from_spec(spec)
sys.modules[spec.name] = query_stock
spec.loader.exec_module(query_stock)


class _FakeResponse:
    status_code = 200

    def raise_for_status(self):
        if self.status_code >= 400:
            raise query_stock.requests.exceptions.RequestException(
                f"HTTP {self.status_code}"
            )

    def json(self):
        return {
            "Time Series (Daily)": {
                "2024-01-01": {
                    "1. open": "1",
                    "2. high": "2",
                    "3. low": "0.5",
                    "4. close": "1.5",
                    "5. volume": "100",
                }
            }
        }


def _make_tool(credentials):
    tool = object.__new__(query_stock.QueryStockTool)
    tool.runtime = SimpleNamespace(credentials=credentials)
    tool.create_text_message = lambda text: ("text", text)
    tool.create_json_message = lambda json: ("json", json)
    return tool


def test_alphavantage_missing_api_key_no_http():
    tool = _make_tool({})
    fake_get = mock.Mock(side_effect=AssertionError("no http"))
    with mock.patch.object(query_stock.requests, "get", fake_get):
        msgs = list(tool._invoke({"code": "IBM"}))
    assert msgs[0][1] == "Alpha Vantage API key is required."
    assert fake_get.call_count == 0


def test_alphavantage_empty_code_no_http():
    tool = _make_tool({"api_key": "secret"})
    fake_get = mock.Mock(side_effect=AssertionError("no http"))
    with mock.patch.object(query_stock.requests, "get", fake_get):
        msgs = list(tool._invoke({"code": ""}))
    assert "stock code" in msgs[0][1]
    assert fake_get.call_count == 0


def test_alphavantage_requests_get_uses_timeout():
    tool = _make_tool({"api_key": "secret"})
    fake_get = mock.Mock(return_value=_FakeResponse())
    with mock.patch.object(query_stock.requests, "get", fake_get):
        list(tool._invoke({"code": "IBM"}))
    assert fake_get.call_args.kwargs.get("timeout") == 10


def test_alphavantage_happy_path():
    tool = _make_tool({"api_key": "secret"})
    fake_get = mock.Mock(return_value=_FakeResponse())
    with mock.patch.object(query_stock.requests, "get", fake_get):
        msgs = list(tool._invoke({"code": "IBM"}))
    assert any(m[0] == "json" for m in msgs)

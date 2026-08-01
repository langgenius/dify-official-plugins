"""In-process tests for tools/judge0ce (pytest-shaped)."""

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

    if "httpx" not in sys.modules:
        httpx_stub = types.ModuleType("httpx")

        class _Resp:
            status_code = 201

            def json(self):
                return {"token": "abc123"}

        httpx_stub.post = lambda *a, **k: _Resp()
        sys.modules["httpx"] = httpx_stub

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
    if _name.startswith("executeCode") or _name.startswith("judge0ce"):
        sys.modules.pop(_name, None)

from importlib import util as _importlib_util  # noqa: E402

spec = _importlib_util.spec_from_file_location(
    "executeCode", _PLUGIN_ROOT / "tools" / "executeCode.py"
)
executeCode = _importlib_util.module_from_spec(spec)
sys.modules[spec.name] = executeCode
spec.loader.exec_module(executeCode)


class _PollResponse:
    status_code = 200

    def json(self):
        return {
            "stdout": "hi",
            "stderr": "",
            "compile_output": "",
            "message": "",
            "status": {"description": "Accepted"},
            "time": "0.01",
            "memory": "1024",
        }


def _make_tool(credentials):
    tool = object.__new__(executeCode.ExecuteCodeTool)
    tool.runtime = SimpleNamespace(credentials=credentials)
    tool.create_text_message = lambda text: ("text", text)
    return tool


def _params():
    return {"language_id": 71, "source_code": "print('hi')", "stdin": ""}


def test_judge0ce_missing_api_key_no_http():
    tool = _make_tool({})
    fake_get = mock.Mock(side_effect=AssertionError("no http"))
    with mock.patch.object(executeCode.requests, "get", fake_get):
        msgs = list(tool._invoke(_params()))
    assert msgs[0][1] == "Judge0 CE RapidAPI key is required."
    assert fake_get.call_count == 0


def test_judge0ce_requests_get_uses_timeout():
    tool = _make_tool({"X-RapidAPI-Key": "secret"})
    fake_get = mock.Mock(return_value=_PollResponse())

    class _SubmitResp:
        status_code = 201

        def json(self):
            return {"token": "abc123"}

    with mock.patch.object(executeCode, "post", return_value=_SubmitResp()):
        with mock.patch.object(executeCode.requests, "get", fake_get):
            list(tool._invoke(_params()))
    assert fake_get.call_args.kwargs.get("timeout") == 10


def test_judge0ce_happy_path():
    tool = _make_tool({"X-RapidAPI-Key": "secret"})
    fake_get = mock.Mock(return_value=_PollResponse())

    class _SubmitResp:
        status_code = 201

        def json(self):
            return {"token": "abc123"}

    with mock.patch.object(executeCode, "post", return_value=_SubmitResp()):
        with mock.patch.object(executeCode.requests, "get", fake_get):
            msgs = list(tool._invoke(_params()))
    assert any(m[0] == "text" and "stdout: hi" in m[1] for m in msgs)

"""In-process tests for tools/devdocs (pytest-shaped).

Mirrors the shape of tools/brave/tests/test_brave.py from PR #3476 and the
judge0ce / alphavantage tests consolidated in PR #3478.

Covers the three pre-fix bugs in searchDevDocs.py:

1. Empty ``doc`` / ``topic`` inputs fall through to a malformed
   ``requests.get`` call instead of returning.
2. ``requests.get`` is called without a ``timeout=``, so a slow upstream
   hangs the worker for the full outer ``MAX_REQUEST_TIMEOUT``.
3. ``response.raise_for_status()`` is not called, so 4xx / 5xx bodies are
   returned to the LLM as if they were successful.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any
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

        def _get(*args, **kwargs):
            raise AssertionError("requests.get must be patched")

        requests_stub.get = _get
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
    if _name.startswith("tools.devdocs") or _name == "searchDevDocs":
        sys.modules.pop(_name, None)

from importlib import util as _importlib_util  # noqa: E402

_spec = _importlib_util.spec_from_file_location(
    "searchDevDocs", _PLUGIN_ROOT / "tools" / "searchDevDocs.py"
)
searchDevDocs = _importlib_util.module_from_spec(_spec)
sys.modules[_spec.name] = searchDevDocs
_spec.loader.exec_module(searchDevDocs)


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        text: str = "",
        raise_exc: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self.text = text
        self._raise_exc = raise_exc

    def raise_for_status(self) -> None:
        if self._raise_exc is not None:
            raise self._raise_exc


def _make_tool() -> Any:
    tool = object.__new__(searchDevDocs.SearchDevDocsTool)
    tool.runtime = SimpleNamespace(credentials={})
    tool.create_text_message = lambda text: ("text", text)
    tool.session = SimpleNamespace(
        model=SimpleNamespace(
            summary=SimpleNamespace(
                invoke=lambda text, instruction: (
                    f"summary<{instruction}>{text}</summary>"
                )
            )
        )
    )
    return tool


def test_empty_doc_returns_without_http() -> None:
    tool = _make_tool()
    fake_get = mock.Mock(side_effect=AssertionError("no http"))
    with mock.patch.object(searchDevDocs.requests, "get", fake_get):
        msgs = list(tool._invoke({"doc": "", "topic": "html"}))
    assert msgs[0][1] == "Please provide the documentation name."
    assert fake_get.call_count == 0


def test_empty_topic_returns_without_http() -> None:
    tool = _make_tool()
    fake_get = mock.Mock(side_effect=AssertionError("no http"))
    with mock.patch.object(searchDevDocs.requests, "get", fake_get):
        msgs = list(tool._invoke({"doc": "python", "topic": ""}))
    assert msgs[0][1] == "Please provide the topic path."
    assert fake_get.call_count == 0


def test_requests_get_uses_timeout() -> None:
    tool = _make_tool()
    fake_get = mock.Mock(return_value=_FakeResponse(status_code=200, text="<html/>"))
    with mock.patch.object(searchDevDocs.requests, "get", fake_get):
        list(tool._invoke({"doc": "python", "topic": "library/functions"}))
    assert fake_get.call_args.kwargs.get("timeout") == 10


def test_request_exception_surfaces_clear_error() -> None:
    tool = _make_tool()
    fake_get = mock.Mock(
        side_effect=searchDevDocs.requests.exceptions.RequestException("boom")
    )
    with mock.patch.object(searchDevDocs.requests, "get", fake_get):
        msgs = list(tool._invoke({"doc": "python", "topic": "library/functions"}))
    assert any(m[0] == "text" and "boom" in m[1] for m in msgs)


def test_4xx_response_raises_for_status_and_surfaces_error() -> None:
    tool = _make_tool()
    fake_response = _FakeResponse(
        status_code=404,
        text="not found",
        raise_exc=searchDevDocs.requests.exceptions.RequestException("404"),
    )
    fake_get = mock.Mock(return_value=fake_response)
    with mock.patch.object(searchDevDocs.requests, "get", fake_get):
        msgs = list(tool._invoke({"doc": "python", "topic": "library/functions"}))
    fake_get.assert_called_once()
    assert any(m[0] == "text" and "404" in m[1] for m in msgs)


def test_happy_path_passes_body_to_summary() -> None:
    tool = _make_tool()
    fake_get = mock.Mock(
        return_value=_FakeResponse(status_code=200, text="<html>body</html>")
    )
    with mock.patch.object(searchDevDocs.requests, "get", fake_get):
        msgs = list(tool._invoke({"doc": "python", "topic": "library/functions"}))
    assert any(m[0] == "text" and "<html>body</html>" in m[1] for m in msgs)

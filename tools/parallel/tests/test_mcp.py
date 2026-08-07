from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from tools import _mcp


def test_normalize_result_prefers_structured_content() -> None:
    result = SimpleNamespace(
        isError=False,
        structuredContent={"search_id": "search-1", "results": []},
        content=[SimpleNamespace(type="text", text="ignored")],
    )
    assert _mcp.normalize_result(result) == {"search_id": "search-1", "results": []}


def test_normalize_result_unwraps_fastmcp_result() -> None:
    result = SimpleNamespace(
        isError=False,
        structuredContent={"result": {"extract_id": "extract-1"}},
        content=[],
    )
    assert _mcp.normalize_result(result) == {"extract_id": "extract-1"}


def test_normalize_result_raises_text_error() -> None:
    result = SimpleNamespace(
        isError=True,
        structuredContent=None,
        content=[SimpleNamespace(type="text", text="rate limited")],
    )
    with pytest.raises(RuntimeError, match="rate limited"):
        _mcp.normalize_result(result)


@pytest.mark.asyncio
async def test_call_parallel_tool_uses_fixed_endpoint_and_exact_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[object] = []

    @asynccontextmanager
    async def fake_transport(url: str):
        events.append(("transport", url))
        yield object(), object(), None

    class FakeSession:
        def __init__(self, *_: object) -> None:
            events.append("session")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def initialize(self) -> None:
            events.append("initialize")

        async def call_tool(self, name: str, arguments: dict):
            events.append(("call", name, arguments))
            return SimpleNamespace(
                isError=False,
                structuredContent={"results": []},
                content=[],
            )

    monkeypatch.setattr(_mcp, "streamable_http_client", fake_transport)
    monkeypatch.setattr(_mcp, "ClientSession", FakeSession)

    result = await _mcp.call_parallel_tool(
        "web_search", {"objective": "current release", "search_queries": ["release"]}
    )

    assert result == {"results": []}
    assert events == [
        ("transport", "https://search.parallel.ai/mcp"),
        "session",
        "initialize",
        (
            "call",
            "web_search",
            {"objective": "current release", "search_queries": ["release"]},
        ),
    ]


@pytest.mark.asyncio
async def test_call_parallel_tool_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        await _mcp.call_parallel_tool("delete_everything", {})  # type: ignore[arg-type]

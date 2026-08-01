import json
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

_MCP_URL = "https://search.parallel.ai/mcp"
_ALLOWED_TOOLS = frozenset({"web_search", "web_fetch"})

ParallelToolName = Literal["web_search", "web_fetch"]
ParallelResult = dict[str, Any] | list[Any] | str


def clean_string_list(value: Any, *, field: str) -> list[str]:
    """Normalize Dify array inputs and reject empty required collections."""
    if isinstance(value, str):
        values: Sequence[Any] = value.split(",")
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        values = value
    else:
        values = ()

    cleaned = [str(item).strip() for item in values if str(item).strip()]
    if not cleaned:
        raise ValueError(f"{field} must contain at least one value")
    return cleaned


def optional_string(value: Any, *, field: str, max_length: int) -> str | None:
    """Normalize an optional MCP string while preserving its server limit."""
    cleaned = str(value or "").strip()
    if not cleaned:
        return None
    if len(cleaned) > max_length:
        raise ValueError(f"{field} must be at most {max_length} characters")
    return cleaned


def _text_content(result: Any) -> str | None:
    parts = [
        item.text
        for item in getattr(result, "content", ())
        if getattr(item, "type", None) == "text" and getattr(item, "text", None)
    ]
    return "\n".join(parts) if parts else None


def normalize_result(result: Any) -> ParallelResult:
    """Prefer MCP structured output and fall back to successful text content."""
    text = _text_content(result)
    if getattr(result, "isError", False):
        raise RuntimeError(text or "Parallel Search MCP tool call failed")

    structured = getattr(result, "structuredContent", None)
    if structured is None:
        structured = getattr(result, "structured_content", None)
    if isinstance(structured, (dict, list)):
        if isinstance(structured, dict) and set(structured) == {"result"}:
            nested = structured["result"]
            if isinstance(nested, (dict, list, str)):
                return nested
        return structured

    if text is None:
        raise RuntimeError("Parallel Search MCP returned no structured or text content")
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        return text
    return decoded if isinstance(decoded, (dict, list, str)) else text


async def call_parallel_tool(
    name: ParallelToolName, arguments: dict[str, Any]
) -> ParallelResult:
    """Call one allowlisted tool on Parallel's fixed anonymous MCP endpoint."""
    if name not in _ALLOWED_TOOLS:
        raise ValueError(f"Unsupported Parallel MCP tool: {name}")

    async with (
        streamable_http_client(_MCP_URL) as (
            read_stream,
            write_stream,
            _,
        ),
        ClientSession(read_stream, write_stream) as session,
    ):
        await session.initialize()
        result = await session.call_tool(name, arguments)
    return normalize_result(result)


def result_summary(name: ParallelToolName, result: ParallelResult) -> str | None:
    """Build a compact human-readable index without duplicating long excerpts."""
    if not isinstance(result, Mapping):
        return None

    results = result.get("results")
    if not isinstance(results, list):
        return None

    heading = "Search results" if name == "web_search" else "Fetched URLs"
    lines = [f"## {heading}"]
    for item in results:
        if not isinstance(item, Mapping):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        title = str(item.get("title") or url).strip()
        lines.append(f"- [{title}]({url})")
    return "\n".join(lines) if len(lines) > 1 else None

import asyncio
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from ._mcp import (
    call_parallel_tool,
    clean_string_list,
    optional_string,
    result_summary,
)


def build_search_arguments(tool_parameters: dict[str, Any]) -> dict[str, Any]:
    objective = str(tool_parameters.get("objective") or "").strip()
    if not objective:
        raise ValueError("objective is required")
    arguments = {
        "objective": objective,
        "search_queries": clean_string_list(
            tool_parameters.get("search_queries"), field="search_queries"
        ),
    }
    session_id = optional_string(
        tool_parameters.get("session_id"), field="session_id", max_length=100
    )
    if session_id:
        arguments["session_id"] = session_id
    return arguments


class WebSearchTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        result = asyncio.run(
            call_parallel_tool("web_search", build_search_arguments(tool_parameters))
        )
        if isinstance(result, (dict, list)):
            yield self.create_json_message(result)
            summary = result_summary("web_search", result)
            if summary:
                yield self.create_text_message(summary)
        else:
            yield self.create_text_message(result)

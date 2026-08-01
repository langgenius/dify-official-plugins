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


def build_fetch_arguments(tool_parameters: dict[str, Any]) -> dict[str, Any]:
    urls = clean_string_list(tool_parameters.get("urls"), field="urls")
    if len(urls) > 20:
        raise ValueError("urls must contain at most 20 values")
    arguments: dict[str, Any] = {"urls": urls}
    objective = optional_string(
        tool_parameters.get("objective"), field="objective", max_length=200
    )
    if objective:
        arguments["objective"] = objective
    queries = tool_parameters.get("search_queries")
    if queries:
        arguments["search_queries"] = clean_string_list(queries, field="search_queries")
    if tool_parameters.get("full_content") is True:
        arguments["full_content"] = True
    session_id = optional_string(
        tool_parameters.get("session_id"), field="session_id", max_length=100
    )
    if session_id:
        arguments["session_id"] = session_id
    return arguments


class WebFetchTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        result = asyncio.run(
            call_parallel_tool("web_fetch", build_fetch_arguments(tool_parameters))
        )
        if isinstance(result, (dict, list)):
            yield self.create_json_message(result)
            summary = result_summary("web_fetch", result)
            if summary:
                yield self.create_text_message(summary)
        else:
            yield self.create_text_message(result)

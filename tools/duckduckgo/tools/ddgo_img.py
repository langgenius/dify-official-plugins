from typing import Any, Generator

from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool

from tools.ddgs_utils import search_with_retry

# ddgs aggregates several image backends and they disagree on the time-range vocabulary:
# the Bing engine expects "day"/"week"/"month"/"year" while the DuckDuckGo engine expects
# "d"/"w"/"m"/"y". Engines that reject the value are skipped silently, so we send the Bing
# vocabulary -- the DuckDuckGo image engine is currently broken upstream and serves nothing.
TIMELIMIT_MAP = {"Day": "day", "Week": "week", "Month": "month", "Year": "year"}


class DuckDuckGoImageSearchTool(Tool):
    """
    Tool for performing an image search using DuckDuckGo search engine.
    """

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        query = tool_parameters.get("query")
        timelimit = tool_parameters.get("timelimit")
        query_dict = {
            "timelimit": TIMELIMIT_MAP.get(timelimit, timelimit),
            "size": tool_parameters.get("size"),
            "max_results": tool_parameters.get("max_results"),
        }
        # ddgs treats an explicit None size as a real filter value, so drop empty options.
        query_dict = {k: v for k, v in query_dict.items() if v is not None}
        proxy = tool_parameters.get("proxy_server", None)
        backend = tool_parameters.get("backend", None)
        response = search_with_retry("images", query, proxy=proxy, backend=backend, **query_dict)
        for res in response:
            # Yield IMAGE rather than IMAGE_LINK. Dify only derives a tool_file_id for an
            # IMAGE_LINK by matching its URL against its own /files/tools/ route, so a remote
            # search result would arrive without one and the agent node rejects it with
            # "missing tool_file_id metadata". IMAGE makes Dify fetch the remote URL, register a
            # tool file for it, and re-emit the IMAGE_LINK itself, keeping the meta below.
            yield ToolInvokeMessage(
                type=ToolInvokeMessage.MessageType.IMAGE,
                message=ToolInvokeMessage.TextMessage(text=res.get("image")),
                meta=res,
            )

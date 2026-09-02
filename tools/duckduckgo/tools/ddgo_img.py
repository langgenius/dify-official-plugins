from enum import Enum
from typing import Any, Generator

from ddgs import DDGS

from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool

# ddgs aggregates several image backends and they disagree on the time-range vocabulary:
# the Bing engine expects "day"/"week"/"month"/"year" while the DuckDuckGo engine expects
# "d"/"w"/"m"/"y". Engines that reject the value are skipped silently, so we send the Bing
# vocabulary -- the DuckDuckGo image engine is currently broken upstream and serves nothing.
TIMELIMIT_MAP = {"Day": "day", "Week": "week", "Month": "month", "Year": "year"}


class FileTransferMethod(str, Enum):
    REMOTE_URL = "remote_url"
    LOCAL_FILE = "local_file"
    TOOL_FILE = "tool_file"

    @staticmethod
    def value_of(value):
        for member in FileTransferMethod:
            if member.value == value:
                return member
        raise ValueError(f"No matching enum found for value '{value}'")


class DuckDuckGoImageSearchTool(Tool):
    """
    Tool for performing an image search using DuckDuckGo search engine.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
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
        response = DDGS(proxy=proxy).images(query, **query_dict)
        for res in response:
            res["transfer_method"] = FileTransferMethod.REMOTE_URL
            msg = ToolInvokeMessage(
                type=ToolInvokeMessage.MessageType.IMAGE_LINK,
                message=ToolInvokeMessage.TextMessage(text=res.get("image")),
                meta=res,
            )
            yield msg

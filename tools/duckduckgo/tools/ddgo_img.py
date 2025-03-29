from enum import Enum
from typing import Any, Generator

from duckduckgo_search import DDGS

from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


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
        query_dict = {
            "keywords": tool_parameters.get("query"),
            "timelimit": tool_parameters.get("timelimit"),
            "size": tool_parameters.get("size"),
            "max_results": tool_parameters.get("max_results"),
        }
        proxy = tool_parameters.get("proxy_server", None)
        response = DDGS(proxy=proxy).images(**query_dict) if proxy else DDGS().images(**query_dict)
        for res in response:
            res["transfer_method"] = FileTransferMethod.REMOTE_URL
            msg = ToolInvokeMessage(
                type=ToolInvokeMessage.MessageType.IMAGE_LINK,
                message=res.get("image"),
                save_as="",
                meta=res,
            )
            yield msg

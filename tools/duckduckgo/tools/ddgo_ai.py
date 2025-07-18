from typing import Any, Generator

from duckduckgo_search import DDGS

from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class DuckDuckGoAITool(Tool):
    """
    Tool for performing a search using DuckDuckGo search engine.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        query_dict = {
            "keywords": tool_parameters.get("query"),
            "model": tool_parameters.get("model"),
        }
        proxy = tool_parameters.get("proxy_server", None)
        response = DDGS(proxy=proxy).chat(**query_dict) if proxy else DDGS().chat(**query_dict)
        yield self.create_text_message(text=response)

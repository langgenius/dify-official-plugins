from typing import Any, Generator

from duckduckgo_search import DDGS

from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class DuckDuckGoTranslateTool(Tool):
    """
    Tool for performing a search using DuckDuckGo search engine.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        query_dict = {
            "keywords": tool_parameters.get("query"),
            "to": tool_parameters.get("translate_to"),
        }
        proxy = tool_parameters.get("proxy_server", None)
        if proxy:
            response = (DDGS(proxy=proxy).translate(**query_dict)[0].get("translated", "Unable to translate!"))
        else:
            response = (DDGS().translate(**query_dict)[0].get("translated", "Unable to translate!"))
        yield self.create_text_message(text=response)

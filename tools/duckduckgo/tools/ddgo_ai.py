from typing import Any, Generator

from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class DuckDuckGoAITool(Tool):
    """
    Deprecated. DuckDuckGo AI Chat is no longer reachable from this plugin.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        raise NotImplementedError(
            "DuckDuckGo AI Chat is no longer supported by this plugin. DuckDuckGo changed the "
            "duckai endpoint and the search library this plugin now uses (ddgs) provides no chat "
            "API. Use a dedicated LLM node or model provider instead."
        )
        yield  # pragma: no cover - keeps this a generator function

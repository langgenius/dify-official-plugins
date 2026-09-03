from typing import Any, Generator

from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class DuckDuckGoTranslateTool(Tool):
    """
    Deprecated. DuckDuckGo's translate endpoint is no longer available.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        raise NotImplementedError(
            "DuckDuckGo Translate is no longer supported by this plugin. The upstream search "
            "library dropped the translate endpoint and DuckDuckGo no longer exposes it. Use a "
            "dedicated translation tool or an LLM node instead."
        )
        yield  # pragma: no cover - keeps this a generator function

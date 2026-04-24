from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool

from .firecrawl_appx import FirecrawlApp


class MapTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        the api doc:
        https://docs.firecrawl.dev/api-reference/endpoint/map
        """
        app = FirecrawlApp(
            api_key=self.runtime.credentials.get("firecrawl_api_key"), base_url=self.runtime.credentials.get("base_url")
        )
        payload = {}
        payload["search"] = tool_parameters.get("search")
        payload["ignoreSitemap"] = tool_parameters.get("ignoreSitemap", True)
        payload["includeSubdomains"] = tool_parameters.get("includeSubdomains", False)
        payload["limit"] = tool_parameters.get("limit", 5000)
        map_result = app.map(url=tool_parameters["url"], **payload)
        yield self.create_json_message(map_result)

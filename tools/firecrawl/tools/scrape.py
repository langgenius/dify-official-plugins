from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from .firecrawl_appx import FirecrawlApp, get_array_params, get_json_params


class ScrapeTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        the api doc:
        https://docs.firecrawl.dev/api-reference/endpoint/scrape
        """
        app = FirecrawlApp(
            api_key=self.runtime.credentials.get("firecrawl_api_key"), base_url=self.runtime.credentials.get("base_url")
        )
        payload = {}
        extract = {}
        payload["formats"] = get_array_params(tool_parameters, "formats")
        payload["onlyMainContent"] = tool_parameters.get("onlyMainContent", True)
        payload["includeTags"] = get_array_params(tool_parameters, "includeTags")
        payload["excludeTags"] = get_array_params(tool_parameters, "excludeTags")
        payload["headers"] = get_json_params(tool_parameters, "headers")
        payload["waitFor"] = tool_parameters.get("waitFor", 0)
        payload["timeout"] = tool_parameters.get("timeout", 30000)
        extract["schema"] = get_json_params(tool_parameters, "schema")
        extract["systemPrompt"] = tool_parameters.get("systemPrompt")
        extract["prompt"] = tool_parameters.get("prompt")
        extract = {k: v for (k, v) in extract.items() if v not in (None, "")}
        payload["extract"] = extract or None
        payload = {k: v for (k, v) in payload.items() if v not in (None, "")}
        crawl_result = app.scrape_url(url=tool_parameters["url"], **payload)
        markdown_result = crawl_result.get("data", {}).get("markdown", "")
        yield self.create_text_message(markdown_result)
        yield self.create_json_message(crawl_result)

from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from .firecrawl_appx import FirecrawlApp


def _get_array_params(tool_parameters: dict[str, Any], key: str):
    param = tool_parameters.get(key)
    if not param:
        return None
    if isinstance(param, list):
        values = param
    else:
        values = str(param).split(",")
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    return cleaned or None


def _get_format_objects(tool_parameters: dict[str, Any], key: str):
    formats = _get_array_params(tool_parameters, key)
    if not formats:
        return None
    return [{"type": format_name} for format_name in formats]


class SearchTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        the api doc:
        https://docs.firecrawl.dev/api-reference/endpoint/search
        """
        app = FirecrawlApp(
            api_key=self.runtime.credentials.get("firecrawl_api_key"), base_url=self.runtime.credentials.get("base_url")
        )

        scrape_options = {}
        scrape_formats = _get_format_objects(tool_parameters, "scrapeFormats")
        if scrape_formats:
            scrape_options["formats"] = scrape_formats
            only_main_content = tool_parameters.get("onlyMainContent")
            if only_main_content is not None:
                scrape_options["onlyMainContent"] = only_main_content

        payload = {}
        payload["limit"] = tool_parameters.get("limit", 10)
        payload["sources"] = _get_array_params(tool_parameters, "sources")
        payload["categories"] = _get_array_params(tool_parameters, "categories")
        payload["includeDomains"] = _get_array_params(tool_parameters, "includeDomains")
        payload["excludeDomains"] = _get_array_params(tool_parameters, "excludeDomains")
        payload["tbs"] = tool_parameters.get("tbs")
        payload["location"] = tool_parameters.get("location")
        payload["country"] = tool_parameters.get("country")
        payload["timeout"] = tool_parameters.get("timeout")
        payload["ignoreInvalidURLs"] = tool_parameters.get("ignoreInvalidURLs")
        payload["enterprise"] = _get_array_params(tool_parameters, "enterprise")
        payload["scrapeOptions"] = scrape_options or None
        payload = {k: v for (k, v) in payload.items() if v not in (None, "")}

        search_result = app.search(query=tool_parameters["query"], **payload)
        yield self.create_json_message(search_result)

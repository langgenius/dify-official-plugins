from typing import Any, Generator, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from spiderApp import RequestParamsDict, Spider

DEFAULT_LIMIT = 10
DEFAULT_DEPTH = 25


def parse_patterns(value: Any) -> Optional[list[str]]:
    """Turn the comma-separated form value into the list the API expects."""
    if value is None:
        return None
    if isinstance(value, list):
        items = [str(v).strip() for v in value]
    else:
        items = [part.strip() for part in str(value).split(",")]
    items = [item for item in items if item]
    return items or None


def to_int(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def build_options(tool_parameters: dict[str, Any]) -> RequestParamsDict:
    options: RequestParamsDict = {
        "limit": to_int(tool_parameters.get("limit"), DEFAULT_LIMIT),
        "depth": to_int(tool_parameters.get("depth"), DEFAULT_DEPTH),
        "readability": bool(tool_parameters.get("readability", False)),
    }
    blacklist = parse_patterns(tool_parameters.get("blacklist"))
    if blacklist:
        options["blacklist"] = blacklist
    whitelist = parse_patterns(tool_parameters.get("whitelist"))
    if whitelist:
        options["whitelist"] = whitelist
    return options


def format_pages(pages: Any) -> str:
    if isinstance(pages, dict):
        pages = [pages]
    if not isinstance(pages, list):
        return ""
    result = ""
    for page in pages:
        if not isinstance(page, dict):
            continue
        result += "URL: " + str(page.get("url") or "") + "\n"
        result += "CONTENT: " + str(page.get("content") or "") + "\n\n"
    return result


class ScrapeTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        app = Spider(api_key=self.runtime.credentials["spider_api_key"])
        url = tool_parameters["url"]
        mode = tool_parameters.get("mode") or "crawl"
        options = build_options(tool_parameters)

        try:
            if mode == "scrape":
                pages = app.scrape_url(url=url, params=options)
            else:
                pages = app.crawl_url(url=url, params=options)
        except Exception as e:
            yield self.create_text_message(f"Spider request failed: {e}")
            return

        yield self.create_text_message(format_pages(pages))

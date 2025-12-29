import logging
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

CUSTOM_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"

PARAMETER_KEYS = [
    "q",
    "c2coff",
    "cr",
    "cx",
    "dateRestrict",
    "exactTerms",
    "excludeTerms",
    "fileType",
    "filter",
    "gl",
    "lowRange",
    "highRange",
    "hl",
    "hq",
    "imgColorType",
    "imgDominantColor",
    "imgSize",
    "imgType",
    "linkSite",
    "lr",
    "num",
    "start",
    "orTerms",
    "rights",
    "safe",
    "searchType",
    "siteSearch",
    "siteSearchFilter",
    "sort",
]


class GoogleSearchTool(Tool):

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        params = {
            "key": self.runtime.credentials.get("key"),
            "cx": self.runtime.credentials.get("cx"),
        }
        for parameter_key in PARAMETER_KEYS:
            if parameter_key in tool_parameters and tool_parameters[parameter_key] != "":
                params.update({parameter_key: tool_parameters[parameter_key]})
        try:
            response = requests.get(CUSTOM_SEARCH_URL, params=params)
            response.raise_for_status()
            response_json = response.json()

            results = response_json.get("items", [])
            yield self.create_json_message(results)

        except Exception as e:
            logging.error("Failed google search %s, %s", tool_parameters, e, exc_info=True)
            yield self.create_text_message(f"Failed to google search, error: {type(e).__name__}")

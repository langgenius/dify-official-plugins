from __future__ import annotations

from typing import Any, Generator
import re
import requests
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool

SEARCH_API_URL = "https://www.searchapi.io/api/v1/search"

# ISO 639-1 language code (two ASCII letters, e.g. "en", "zh"). SearchAPI rejects
# anything else with a 422; we guard early to avoid the round trip.
_HL_RE = re.compile(r"^[A-Za-z]{2}$")
# ISO 3166-1 alpha-2 country code (two ASCII letters, e.g. "us", "de").
_GL_RE = re.compile(r"^[A-Za-z]{2}$")


class SearchAPI:
    """
    SearchAPI tool provider.
    """

    def __init__(self, api_key: str) -> None:
        """Initialize SearchAPI tool provider."""
        self.searchapi_api_key = api_key

    def run(self, query: str, **kwargs: Any) -> str:
        """Run query through SearchAPI and parse result."""
        type = kwargs.get("result_type", "text")
        return self._process_response(self.results(query, **kwargs), type=type)

    def results(self, query: str, **kwargs: Any) -> dict:
        """Run query through SearchAPI and return the raw result."""
        params = self.get_params(query, **kwargs)
        response = requests.get(
            url=SEARCH_API_URL,
            params=params,
            headers={"Authorization": f"Bearer {self.searchapi_api_key}"},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def get_params(self, query: str, **kwargs: Any) -> dict[str, str]:
        """Get parameters for SearchAPI."""
        return {
            "engine": "google_news",
            "q": query,
            **{key: value for (key, value) in kwargs.items() if value not in {None, ""}},
        }

    @staticmethod
    def _process_response(res: dict, type: str) -> str:
        """Process response from SearchAPI."""
        if "error" in res:
            return res["error"]
        toret = ""
        if type == "text":
            if "organic_results" in res and "snippet" in res["organic_results"][0]:
                for item in res["organic_results"]:
                    toret += "content: " + item["snippet"] + "\n" + "link: " + item["link"] + "\n"
            if "top_stories" in res and "title" in res["top_stories"][0]:
                for item in res["top_stories"]:
                    toret += "title: " + item["title"] + "\n" + "link: " + item["link"] + "\n"
            if toret == "":
                toret = "No good search result found"
        elif type == "link":
            if "organic_results" in res and "title" in res["organic_results"][0]:
                for item in res["organic_results"]:
                    toret += f"[{item['title']}]({item['link']})\n"
            elif "top_stories" in res and "title" in res["top_stories"][0]:
                for item in res["top_stories"]:
                    toret += f"[{item['title']}]({item['link']})\n"
            else:
                toret = "No good search result found"
        return toret


class GoogleNewsTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invoke the SearchApi tool.
        """
        api_key = self.runtime.credentials.get("searchapi_api_key")
        if not api_key:
            yield self.create_text_message("SearchAPI API key is required.")
            return

        gl = tool_parameters.get("gl", "us")
        hl = tool_parameters.get("hl", "en")
        if not _GL_RE.match(gl or ""):
            yield self.create_text_message(
                f"Invalid 'gl' parameter: {gl!r}. Expected a two-letter ISO 3166-1 country code."
            )
            return
        if not _HL_RE.match(hl or ""):
            yield self.create_text_message(
                f"Invalid 'hl' parameter: {hl!r}. Expected a two-letter ISO 639-1 language code."
            )
            return

        query = tool_parameters["query"]
        result_type = tool_parameters["result_type"]
        num = tool_parameters.get("num", 10)
        google_domain = tool_parameters.get("google_domain", "google.com")
        location = tool_parameters.get("location")
        try:
            result = SearchAPI(api_key).run(
                query,
                result_type=result_type,
                num=num,
                google_domain=google_domain,
                gl=gl,
                hl=hl,
                location=location,
            )
        except requests.exceptions.RequestException as exc:
            yield self.create_text_message(
                f"An error occurred while invoking the tool: {exc}."
            )
            return
        if result_type == "text":
            yield self.create_text_message(text=result)
        yield self.create_link_message(link=result)

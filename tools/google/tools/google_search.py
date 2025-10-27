from collections.abc import Generator
from contextlib import suppress
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.utils import to_refs, VALID_LANGUAGES, VALID_COUNTRIES, InstantSearchResponse


def _parse_results(results: dict) -> dict:
    """
    [deprecated function]
    :param results:
    :return:
    """
    result = {}
    if "knowledge_graph" in results:
        result["title"] = results["knowledge_graph"].get("title", "")
        result["description"] = results["knowledge_graph"].get("description", "")
    if "organic_results" in results:
        result["organic_results"] = [
            {
                "title": item.get("title", ""),
                "link": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            }
            for item in results["organic_results"]
        ]
    return result


class GoogleSearchTool(Tool):
    SERP_API_URL = "https://serpapi.com/search"

    @staticmethod
    def _set_params_language_code(params: dict, tool_parameters: dict):
        with suppress(Exception):
            language_code = tool_parameters.get("language_code") or tool_parameters.get("hl")
            if (
                language_code
                and isinstance(language_code, str)
                and isinstance(VALID_LANGUAGES, set)
                and language_code in VALID_LANGUAGES
            ):
                params["hl"] = language_code

    @staticmethod
    def _set_params_country_code(params: dict, tool_parameters: dict):
        with suppress(Exception):
            country_code = tool_parameters.get("country_code") or tool_parameters.get("gl")
            if (
                country_code
                and isinstance(country_code, str)
                and VALID_COUNTRIES
                and isinstance(VALID_COUNTRIES, set)
                and country_code in VALID_COUNTRIES
            ):
                params["gl"] = country_code

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        as_agent_tool = tool_parameters.get("as_agent_tool", False)

        query = tool_parameters.get("query", "")
        params = {
            "api_key": self.runtime.credentials["serpapi_api_key"],
            "q": query,
            "engine": "google",
            "google_domain": "google.com",
            "num": 10,
        }
        self._set_params_country_code(params, tool_parameters)
        self._set_params_language_code(params, tool_parameters)

        try:
            response = requests.get(url=self.SERP_API_URL, params=params)
            response.raise_for_status()

            isr = InstantSearchResponse(refs=to_refs(response.json()))

            if not as_agent_tool:
                yield self.create_json_message(json=isr.to_dify_json_message())
            else:
                yield self.create_text_message(text=isr.to_dify_text_message())

            # valuable_res = self._parse_results(response.json())
            # yield self.create_json_message(valuable_res)
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(
                f"An error occurred while invoking the tool: {str(e)}. "
                "Please refer to https://serpapi.com/locations-api for the list of valid locations."
            )
        except Exception as e:
            yield self.create_text_message(f"An error occurred while invoking the tool: {str(e)}.")

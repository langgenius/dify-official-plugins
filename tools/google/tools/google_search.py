from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from loguru import logger

from tools.utils import to_refs, VALID_LANGUAGES, VALID_COUNTRIES, InstantSearchResponse


def _parse_results(results: dict) -> dict:
    """
    [deprecated function]
    Parse search results into legacy format for backward compatibility.
    The new response protocol wraps data in new fields (refs), but we keep the old fields
    to prevent unexpected issues with existing integrations.
    
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
        try:
            language_code = tool_parameters.get("language_code") or tool_parameters.get("hl")
            if (
                language_code
                and isinstance(language_code, str)
                and isinstance(VALID_LANGUAGES, set)
                and language_code in VALID_LANGUAGES
            ):
                params["hl"] = language_code
        except Exception as e:
            logger.warning(f"Failed to set language code parameter: {e}")

    @staticmethod
    def _set_params_country_code(params: dict, tool_parameters: dict):
        try:
            country_code = tool_parameters.get("country_code") or tool_parameters.get("gl")
            if (
                country_code
                and isinstance(country_code, str)
                and VALID_COUNTRIES
                and isinstance(VALID_COUNTRIES, set)
                and country_code in VALID_COUNTRIES
            ):
                params["gl"] = country_code
        except Exception as e:
            logger.warning(f"Failed to set country code parameter: {e}")

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

            tool_invoke_results = response.json()

            isr = InstantSearchResponse(refs=to_refs(tool_invoke_results))

            if not as_agent_tool:
                isr_json_parts = isr.to_dify_json_message()
                # Merge deprecated fields for backward compatibility
                # The new protocol uses 'refs' to wrap the response, but legacy fields are retained
                # to prevent unexpected issues with existing workflows
                if deprecated_parts := _parse_results(tool_invoke_results):
                    isr_json_parts.update(deprecated_parts)
                yield self.create_json_message(json=isr_json_parts)
            else:
                yield self.create_text_message(text=isr.to_dify_text_message())

        except requests.exceptions.RequestException as e:
            yield self.create_text_message(
                f"An error occurred while invoking the tool: {str(e)}. "
                "Please refer to https://serpapi.com/locations-api for the list of valid locations."
            )
        except Exception as e:
            yield self.create_text_message(f"An error occurred while invoking the tool: {str(e)}.")

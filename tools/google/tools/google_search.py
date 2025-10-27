import json
from collections.abc import Generator
from contextlib import suppress
from pathlib import Path
from typing import Any, Set

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


def load_valid_countries(filepath: Path) -> set | None:
    """
    Load valid country codes from google-countries.json
    :param filepath:
    :return:
    """
    with suppress(Exception):
        if countries := json.loads(filepath.read_text(encoding="utf8")):
            return {country["country_code"] for country in countries}
    return None


def load_valid_languages(filepath: Path) -> set | None:
    """
    Load valid language codes from google-languages.json
    :param filepath:
    :return:
    """
    with suppress(Exception):
        if languages := json.loads(filepath.read_text(encoding="utf8")):
            return {language["language_code"] for language in languages}
    return None


PROJECT_PATH = Path(__file__).parent
VALID_COUNTRIES: Set[str] | None = load_valid_countries(
    PROJECT_PATH.joinpath("google-countries.json")
)
VALID_LANGUAGES: Set[str] | None = load_valid_languages(
    PROJECT_PATH.joinpath("google-languages.json")
)


class GoogleSearchTool(Tool):
    SERP_API_URL = "https://serpapi.com/search"

    @staticmethod
    def _parse_results(results: dict) -> dict:
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
            valuable_res = self._parse_results(response.json())
            yield self.create_json_message(valuable_res)
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(
                f"An error occurred while invoking the tool: {str(e)}. "
                "Please refer to https://serpapi.com/locations-api for the list of valid locations."
            )

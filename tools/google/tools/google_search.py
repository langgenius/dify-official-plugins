import json

from collections.abc import Generator
from typing import Any

import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

import os

SERP_API_URL = "https://serpapi.com/search"


def get_file_path(filename: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)


# Load valid country codes from google-countries.json
def load_valid_countries(filename: str) -> set:
    with open(filename) as file:
        countries = json.load(file)
        return {country['country_code'] for country in countries}


# Load valid language codes from google-languages.json
def load_valid_languages(filename: str) -> set:
    with open(filename) as file:
        languages = json.load(file)
        return {language['language_code'] for language in languages}


VALID_COUNTRIES = load_valid_countries(get_file_path("google-countries.json"))
VALID_LANGUAGES = load_valid_languages(get_file_path("google-languages.json"))


class GoogleSearchTool(Tool):
    def _parse_response(self, response: dict) -> dict:
        result = {}
        if "knowledge_graph" in response:
            result["title"] = response["knowledge_graph"].get("title", "")
            result["description"] = response["knowledge_graph"].get("description", "")
        if "organic_results" in response:
            result["organic_results"] = [
                {
                    "title": item.get("title", ""),
                    "link": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                }
                for item in response["organic_results"]
            ]
        return result

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        hl = tool_parameters.get("hl", "en")
        gl = tool_parameters.get("gl", "us")
        location = tool_parameters.get("location", "")
        imgsz = tool_parameters.get("imgsz", "m")

        # Validate 'hl' (language) code
        if hl not in VALID_LANGUAGES:
            yield self.create_text_message(
                f"Invalid 'hl' parameter: {hl}. Please refer to https://serpapi.com/google-languages for a list of valid language codes.")

        # Validate 'gl' (country) code
        if gl not in VALID_COUNTRIES:
            yield self.create_text_message(
                f"Invalid 'gl' parameter: {gl}. Please refer to https://serpapi.com/google-countries for a list of valid country codes.")

        params = {
            "api_key": self.runtime.credentials["serpapi_api_key"],
            "q": tool_parameters["query"],
            "engine": "google",
            "google_domain": "google.com",
            "gl": gl,
            "hl": hl,
            "imgsz": imgsz
        }
        if location:
            params["location"] = location
        try:
            response = requests.get(url=SERP_API_URL, params=params)
            response.raise_for_status()
            valuable_res = self._parse_response(response.json())
            yield self.create_json_message(valuable_res)
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(
                f"An error occurred while invoking the tool: {str(e)}. Please refer to https://serpapi.com/locations-api for the list of valid locations.")

import json
import os
from itertools import islice
from typing import Any, Generator

import requests
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


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


SERP_API_URL = "https://serpapi.com/search"
VALID_COUNTRIES = load_valid_countries(get_file_path("google-countries.json"))
VALID_LANGUAGES = load_valid_languages(get_file_path("google-languages.json"))


class GoogleImageSearchTool(Tool):
    def _parse_response(self, response: dict, max_results: int) -> dict:
        result = {}
        if "images_results" in response:
            result["images"] = [
                {
                    "title": item.get("title", ""),
                    "image": item.get("original", ""),
                    "thumbnail": item.get("thumbnail", ""),
                    "url": item.get("link", ""),
                    "height": item.get("original_height", ""),
                    "width": item.get("original_width", ""),
                    "source": item.get("source", ""),
                }
                for item in islice(response["images_results"], max_results)
            ]
        return result

    def _invoke(
            self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        hl = tool_parameters.get("hl", "en")
        gl = tool_parameters.get("gl", "us")
        location = tool_parameters.get("location", "")
        max_results = tool_parameters.get("max_results", 3)

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
            "q": tool_parameters['query'],
            "engine": "google_images",
            "gl": gl,
            "hl": hl,
            "location": location
        }
        try:
            response = requests.get(url=SERP_API_URL, params=params)
            response.raise_for_status()

            valuable_res = self._parse_response(response.json(), max_results)
            markdown_result = "\n\n"
            json_result = []
            for res in valuable_res.get("images", []):
                res['extension'] = f".{res['image'].split('.')[-1]}"
                markdown_result += f"![{res.get('title') or ''}]({res.get('image') or ''})"
                json_result.append(self.create_json_message(res))
            yield from [self.create_text_message(markdown_result)] + json_result
        except requests.exceptions.RequestException as e:
            yield self.create_text_message(
                f"An error occurred while invoking the tool: {str(e)}. Please refer to https://serpapi.com/locations-api for the list of valid locations.")

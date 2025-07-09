from collections.abc import Generator
from typing import Any
import requests
import json

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class listAttributesTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        # Get parameters
        target = tool_parameters.get("target_type", "")  # "lists" or "objects"
        slug = tool_parameters.get("slug", "")

        # Validate required parameters
        if target not in ["lists", "objects"]:
            yield self.create_text_message("Target type must be 'lists' or 'objects'.")
            return

        if not slug:
            yield self.create_text_message(f"{target.capitalize()} slug is required.")
            return

        try:
            # Get credentials
            url = f"https://api.attio.com/v2/{target}/{slug}/attributes"
            api_token = "Bearer " + self.runtime.credentials.get("attio_api_token")

            if url.split("api")[1].find("//") != -1 or len(api_token) < 10:
                yield self.create_text_message(
                    "Attio credentials are not properly configured."
                )
                return

            # Setup headers
            headers = {"Authorization": api_token}

            # Make the request
            response = requests.get(url, headers=headers, timeout=30)

            # Handle response
            if response.status_code == 401:
                yield self.create_text_message(f"Bad request - {response.message}")
                return
            elif response.status_code == 404:
                yield self.create_text_message(
                    f"Failed to get attributes: {response.message}"
                )
                return
            elif response.status_code != 200:
                yield self.create_text_message(
                    f"Failed to retrieve attributes: {response.text}"
                )
                return

            yield self.create_text_message("Attributes found successfully.")
            yield self.create_json_message(response.json())

        except requests.exceptions.Timeout:
            yield self.create_text_message("Request timeout - please try again")
        except requests.exceptions.ConnectionError:
            yield self.create_text_message(
                "Failed to connect to Attio - please check your configuration"
            )
        except Exception as e:
            yield self.create_text_message(f"An error occurred: {str(e)}")

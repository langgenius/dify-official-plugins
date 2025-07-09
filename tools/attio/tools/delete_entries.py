from collections.abc import Generator
from typing import Any
import requests
import json

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class deleteEntriesTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        # Get parameters
        list_slug = tool_parameters.get("list_slug", "")
        entry_id = tool_parameters.get("entry_id", "")

        # Validate required parameters
        if not list_slug or not entry_id:
            yield self.create_text_message("List Slug or Entry ID are required.")
            return

        try:
            # Get credentials
            url = f"https://api.attio.com/v2/lists/{list_slug}/entries/{entry_id}"
            api_token = "Bearer " + self.runtime.credentials.get("attio_api_token")

            if url.split("api")[1].find("//") != -1 or len(api_token) < 10:
                yield self.create_text_message(
                    "Attio credentials are not properly configured."
                )
                return

            # Setup headers
            headers = {
                "Authorization": api_token,
            }

            # Make the request
            response = requests.delete(url, headers=headers, timeout=30)

            # Handle response
            if response.status_code == 401:
                yield self.create_text_message(f"Bad request - {response.message}")
                return
            elif response.status_code == 404:
                yield self.create_text_message(
                    f"Failed to delete entries: {response.message}"
                )
                return
            elif response.status_code != 200:
                yield self.create_text_message(
                    f"Failed to delete entries: {response.text}"
                )
                return

            yield self.create_text_message("Entries deleted successfully.")

        except requests.exceptions.Timeout:
            yield self.create_text_message("Request timeout - please try again")
        except requests.exceptions.ConnectionError:
            yield self.create_text_message(
                "Failed to connect to Attio - please check your configuration"
            )
        except Exception as e:
            yield self.create_text_message(f"An error occurred: {str(e)}")

from collections.abc import Generator
from typing import Any
import requests
import json

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class deleteRecordsTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        # Get parameters
        object_slug = tool_parameters.get("object_slug", "")
        record_id = tool_parameters.get("record_id", "")

        # Validate required parameters
        if not object_slug or not record_id:
            yield self.create_text_message("Object Slug or Record ID are required.")
            return

        try:
            # Get credentials
            url = f"https://api.attio.com/v2/objects/{object_slug}/records/{record_id}"
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
                    f"Failed to delete records: {response.message}"
                )
                return
            elif response.status_code != 200:
                yield self.create_text_message(
                    f"Failed to delete records: {response.text}"
                )
                return

            yield self.create_text_message("Record deleted successfully.")

        except requests.exceptions.Timeout:
            yield self.create_text_message("Request timeout - please try again")
        except requests.exceptions.ConnectionError:
            yield self.create_text_message(
                "Failed to connect to Attio - please check your configuration"
            )
        except Exception as e:
            yield self.create_text_message(f"An error occurred: {str(e)}")

from collections.abc import Generator
from typing import Any
import requests
import json

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class addEntriesTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Add one or multiple entris in a Attio List
        """
        # Get parameters
        list_slug = tool_parameters.get("list_slug", "")
        data = tool_parameters.get("data", "")
        parent_record_id = tool_parameters.get("parent_record_id", "")
        parent_object_slug = tool_parameters.get("parent_object_slug", "")

        # Validate required parameters
        if not list_slug:
            yield self.create_text_message("List slug is required.")
            return

        if not data:
            yield self.create_text_message("Data is required for entries creation.")
            return

        if not parent_record_id or not parent_object_slug:
            yield self.create_text_message(
                "Parent record ID and parent object slug are required."
            )
            return

        # Parse JSON data
        try:
            data = json.loads(data)
        except json.JSONDecodeError as e:
            yield self.create_text_message(f"Invalid JSON data: {str(e)}")
            return

        # Validate data structure
        if data:
            if not isinstance(data, dict):
                yield self.create_text_message(
                    "For entries creation, data must be a dictionary."
                )
                return
        else:
            yield self.create_text_message("Data cannot be empty.")
            return

        try:
            # Get credentials
            url = f"https://api.attio.com/v2/lists/{list_slug}/entries"
            api_token = "Bearer " + self.runtime.credentials.get("attio_api_token")

            if url.split("api")[1].find("//") != -1 or len(api_token) < 10:
                yield self.create_text_message(
                    "Attio credentials are not properly configured."
                )
                return

            # Setup payload
            payload = {
                "data": {
                    "entry_values": data,
                    "parent_record_id": parent_record_id,
                    "parent_object_slug": parent_object_slug,
                }
            }

            # Setup headers
            headers = {"Authorization": api_token, "Content-Type": "application/json"}

            # Make the request
            response = requests.post(url, headers=headers, json=payload, timeout=30)

            # Handle response
            if response.status_code == 400:
                yield self.create_text_message(f"Bad request - {response.message}")
                return
            elif response.status_code == 401:
                yield self.create_text_message(f"Unauthorized - {response.message}")
                return
            elif response.status_code == 404:
                yield self.create_text_message(
                    f"Failed to create entries: {response.message}"
                )
                return
            elif response.status_code != 200:
                yield self.create_text_message(
                    f"Failed to create entries: {response.text}"
                )
                return

            yield self.create_text_message("Entries created successfully.")
            yield self.create_json_message(response.json())

        except requests.exceptions.Timeout:
            yield self.create_text_message("Request timeout - please try again")
        except requests.exceptions.ConnectionError:
            yield self.create_text_message(
                "Failed to connect to Attio - please check your configuration"
            )
        except Exception as e:
            yield self.create_text_message(f"Error creating Entries: {str(e)}")

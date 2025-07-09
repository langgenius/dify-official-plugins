from collections.abc import Generator
from typing import Any
import requests
import json

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class addRecordsTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Add one or multiple records in a Attio Object
        """
        # Get parameters
        object_slug = tool_parameters.get("object_slug", "")
        data = tool_parameters.get("data", "")

        # Validate required parameters
        if not object_slug:
            yield self.create_text_message("Object Slug is required.")
            return

        if not data:
            yield self.create_text_message("Data is required for record creation.")
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
                    "For record creation, data must be a dictionary."
                )
                return
        else:
            yield self.create_text_message("Data cannot be empty.")
            return

        try:
            # Get credentials
            url = f"https://api.attio.com/v2/objects/{object_slug}/records"
            api_token = "Bearer " + self.runtime.credentials.get("attio_api_token")

            if url.split("api")[1].find("//") != -1 or len(api_token) < 10:
                yield self.create_text_message(
                    "Attio credentials are not properly configured."
                )
                return

            # Setup payload
            payload = {"data": {"values": data}}

            # Setup headers
            headers = {"Authorization": api_token, "Content-Type": "application/json"}

            # Make the request
            response = requests.post(url, headers=headers, json=payload, timeout=30)

            # Handle response
            if response.status_code == 400:
                yield self.create_text_message(f"Bad request - {response.text}")
                return
            elif response.status_code == 404:
                yield self.create_text_message(
                    f"Failed to create records: {response.text}"
                )
                return
            elif response.status_code != 200:
                yield self.create_text_message(
                    f"Failed to create records: {response.text}"
                )
                return

            yield self.create_text_message("Record created successfully.")
            yield self.create_json_message(response.json())

        except requests.exceptions.Timeout:
            yield self.create_text_message("Request timeout - please try again")
        except requests.exceptions.ConnectionError:
            yield self.create_text_message(
                "Failed to connect to Attio - please check your configuration"
            )
        except Exception as e:
            yield self.create_text_message(f"Error creating records: {str(e)}")

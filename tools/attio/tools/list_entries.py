from collections.abc import Generator
from typing import Any
import requests
import json

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class listEntriesTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        # Get parameters
        list_slug = tool_parameters.get("list_slug", "")
        filters = tool_parameters.get("filters", None)  # optional
        sorts = tool_parameters.get("sorts", None)  # optional
        limit = tool_parameters.get("limit", 500)  # optional
        offset = tool_parameters.get("offset", 0)  # optional

        # Validate required parameters
        if not list_slug:
            yield self.create_text_message("List Slug is required.")
            return

        if filters:
            try:
                filters = json.loads(filters)
                if not isinstance(filters, dict):
                    yield self.create_text_message("Filters must be a JSON object.")
                    return
            except json.JSONDecodeError as e:
                yield self.create_text_message(f"Invalid JSON filters: {str(e)}")
                return

        if sorts:
            try:
                sorts = json.loads(sorts)
                if not isinstance(sorts, list):
                    yield self.create_text_message("Sorts must be a JSON object.")
                    return
            except json.JSONDecodeError as e:
                yield self.create_text_message(f"Invalid JSON sorts: {str(e)}")
                return

        if not isinstance(limit, int) or limit <= 0:
            yield self.create_text_message("Limit must be a positive integer.")
            return
        if not isinstance(offset, int) or offset < 0:
            yield self.create_text_message("Offset must be a non-negative integer.")
            return

        try:
            # Get credentials
            url = f"https://api.attio.com/v2/lists/{list_slug}/entries/query"
            api_token = "Bearer " + self.runtime.credentials.get("attio_api_token")

            if url.split("api")[1].find("//") != -1 or len(api_token) < 10:
                yield self.create_text_message(
                    "Attio credentials are not properly configured."
                )
                return

            # Setup headers and parameters
            headers = {"Authorization": api_token, "Content-Type": "application/json"}

            payloads = {"limit": limit, "offset": offset}
            if filters:
                payloads["filter"] = filters
            if sorts:
                payloads["sorts"] = sorts

            # Make the request
            response = requests.post(url, headers=headers, json=payloads, timeout=30)

            # Handle response
            if response.status_code == 401:
                yield self.create_text_message(
                    f"Unauthorized request - {response.text}"
                )
                return
            elif response.status_code == 404:
                yield self.create_text_message(f"List not found - {response.text}")
                return
            elif response.status_code != 200:
                yield self.create_text_message(
                    f"Failed to retrieve entries: {response.text}"
                )
                return

            yield self.create_text_message("Entries retrieved successfully.")
            yield self.create_json_message(response.json())

        except requests.exceptions.Timeout:
            yield self.create_text_message("Request timeout - please try again")
        except requests.exceptions.ConnectionError:
            yield self.create_text_message(
                "Failed to connect to Attio - please check your configuration"
            )
        except Exception as e:
            yield self.create_text_message(f"An error occurred: {str(e)}")

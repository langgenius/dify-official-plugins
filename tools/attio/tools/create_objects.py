from collections.abc import Generator
from typing import Any
import requests
import json

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class createObjectsTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        try:
            # Get credentials
            url = f"https://api.attio.com/v2/objects/"
            api_token = "Bearer " + self.runtime.credentials.get("attio_api_token")
            api_slug = tool_parameters.get("object_slug", "")  # Only low-case letters
            singular = tool_parameters.get("singular_noun", "")  # Person
            plural = tool_parameters.get("plural_noun", "")  # People

            if url.split("api")[1].find("//") != -1 or len(api_token) < 10:
                yield self.create_text_message(
                    "Attio credentials are not properly configured."
                )
                return

            if not api_slug:
                yield self.create_text_message("Object slug is required.")
                return

            if api_slug != api_slug.lower():
                yield self.create_text_message(
                    "Object slug must be in lower-case letters."
                )
                return

            if not singular or not plural:
                yield self.create_text_message(
                    "Singular and plural nouns are required."
                )
                return

            # Setup headers
            headers = {
                "Authorization": api_token,
                "Content-Type": "application/json",
            }

            # Setup payload
            payload = {
                "data": {
                    "api_slug": api_slug,
                    "singular_noun": singular,
                    "plural_noun": plural,
                }
            }

            # Make the request
            response = requests.post(url, headers=headers, json=payload, timeout=30)

            # Handle response
            if response.status_code == 401:
                yield self.create_text_message(f"Bad request - {response.message}")
                return
            elif response.status_code == 409:
                yield self.create_text_message(
                    f"Failed to create objects: {response.message}"
                )
                return
            elif response.status_code != 200:
                yield self.create_text_message(
                    f"Failed to create objects: {response.text}"
                )
                return

            yield self.create_text_message(
                "Object created successfully. You can now add records to it."
            )
            yield self.create_json_message(response.json())

        except requests.exceptions.Timeout:
            yield self.create_text_message("Request timeout - please try again")
        except requests.exceptions.ConnectionError:
            yield self.create_text_message(
                "Failed to connect to Attio - please check your configuration"
            )
        except Exception as e:
            yield self.create_text_message(f"Error creating object: {str(e)}")

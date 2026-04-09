from typing import Any, Generator
import requests
import base64
import json
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class GiteeAIToolText2Image(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        headers = {"Content-Type": "application/json", "authorization": f"Bearer {self.runtime.credentials['api_key']}"}

        # Get parameters
        width = tool_parameters.get("width", 1024)
        height = tool_parameters.get("height", 1024)
        size = f"{width}x{height}"

        payload = {
            "model": tool_parameters.get("model", "flux-1-schnell"),
            "prompt": tool_parameters.get("inputs"),
            "size": size,
            "n": 1
        }

        url = "https://ai.gitee.com/v1/images/generations"
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            yield self.create_text_message(f"Got Error Response:{response.text}")

        try:
            response_data = response.json()

            # Extract base64 image data from GiteeAI API response
            if "data" in response_data and len(response_data["data"]) > 0:
                image_data = response_data["data"][0]
                if "b64_json" in image_data:
                    base64_image = image_data["b64_json"]
                else:
                    yield self.create_text_message("No image data found in response")
                    return
            else:
                yield self.create_text_message("Invalid response format")
                return

            # Convert base64 to blob
            try:
                # Remove potential data URL prefix if present
                if base64_image.startswith('data:image/'):
                    base64_image = base64_image.split(',')[1]

                # Decode base64 to bytes
                image_bytes = base64.b64decode(base64_image)

                yield self.create_blob_message(
                    blob=image_bytes,
                    meta={"mime_type": "image/jpeg"}
                )

            except Exception as e:
                yield self.create_text_message(f"Failed to decode base64 image data: {str(e)}")

        except json.JSONDecodeError:
            yield self.create_text_message("Failed to parse JSON response")
        except Exception as e:
            yield self.create_text_message(f"Error processing response: {str(e)}")

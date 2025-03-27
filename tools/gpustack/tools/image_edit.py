from base64 import b64decode
from typing import Any, Generator
import requests

from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from dify_plugin.file.file import File, FileType

from .utils import get_base_url, get_common_params, handle_api_error

class ImageEditTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        image: File | None = tool_parameters.get("image")
        if not image:
            raise ValueError("Got no image")
        if image.type != FileType.IMAGE:
            raise ValueError("Not a valid image file")

        try:
            params = get_common_params(tool_parameters)
            params["strength"] = tool_parameters.get("strength", 0.75)

            image_binary = image.blob
            files = {"image": ("image.png", image_binary, "image/png")}

            base_url = get_base_url(self.runtime.credentials["base_url"])
            response = requests.post(
                f"{base_url}/v1/images/edits",
                headers={"Authorization": f"Bearer {self.runtime.credentials['api_key']}"},
                data=params,
                files=files,
                verify=bool(self.runtime.credentials.get("tls_verify", True)),
                timeout=float(tool_parameters.get("timeout")),
            )

            if not response.ok:
                raise Exception(handle_api_error(response))

            for image_data in response.json().get("data", []):
                if image_data.get("b64_json"):
                    yield self.create_blob_message(
                            blob=b64decode(image_data["b64_json"]),
                            meta={"mime_type": "image/png"}
                        )

        except ValueError as e:
            yield self.create_text_message(str(e))
        except Exception as e:
            yield self.create_text_message(f"An error occurred: {str(e)}")

import json
import os
import uuid
from typing import Any, Generator
import httpx
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


from tools.comfyui_client import ComfyUiClient, FileType


class ComfyuiDepthAnything(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        base_url = self.runtime.credentials.get("base_url", "")
        if not base_url:
            yield self.create_text_message("Please input base_url")
        self.cli = ComfyUiClient(base_url)
        model = tool_parameters.get("model", None)
        if not model:
            yield self.create_text_message("Please input model")
            return
        image_server_url = self.runtime.credentials.get("image_server_url", "")
        if not image_server_url:
            yield self.create_text_message("Please input image_server_url")
        images = tool_parameters.get("images") or []
        image_names = []
        for image in images:
            if image.type != FileType.IMAGE:
                continue
            blob = httpx.get(image_server_url.rstrip("/") + image.url, timeout=3)
            image_name = self.cli.post_image(image.filename, blob, image.mime_type)
            if image_name is None:
                raise ToolProviderCredentialValidationError(
                    f"File upload to ComfyUI failed"
                )
            image_names.append(image_name)

        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_dir, "comfyui_depth_anything.json")) as file:
            draw_options = json.load(file)
        draw_options["2"]["inputs"]["model"] = model
        draw_options["3"]["inputs"]["image"] = image_names[0]

        try:
            client_id = str(uuid.uuid4())
            result = self.cli.queue_prompt_image(client_id, prompt=draw_options)
            image = b""
            for node in result:
                for img in result[node]:
                    if img:
                        image = img
                        break
            yield self.create_blob_message(
                blob=image,
                meta={"mime_type": "image/png"},
            )
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to generate image: {str(e)}. Maybe install https://github.com/kijai/ComfyUI-DepthAnythingV2 on ComfyUI"
            )

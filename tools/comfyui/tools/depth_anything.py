import json
import os
import uuid
from typing import Any, Generator
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
        self.comfyui = ComfyUiClient(
            base_url,
            self.runtime.credentials.get("comfyui_api_key")
        )
        model = tool_parameters.get("model", None)
        if not model:
            raise ToolProviderCredentialValidationError("Please input model")

        images = tool_parameters.get("images") or []
        image_names = []
        for image in images:
            if image.type != FileType.IMAGE:
                continue
            image_name = self.comfyui.post_image(
                image.filename, image.blob, image.mime_type)
            image_names.append(image_name)

        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_dir, "comfyui_depth_anything.json")) as file:
            draw_options = json.load(file)
        draw_options["2"]["inputs"]["model"] = model
        draw_options["3"]["inputs"]["image"] = image_names[0]

        try:
            client_id = str(uuid.uuid4())
            result = self.comfyui.queue_prompt_image(
                client_id, prompt=draw_options)
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

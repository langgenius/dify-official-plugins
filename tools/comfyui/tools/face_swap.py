import json
import os
from enum import Enum
from typing import Any, Generator
from dify_plugin.entities.tool import (
    ToolInvokeMessage,
)
from dify_plugin import Tool


from tools.comfyui_client import ComfyUiClient, FileType
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class ModelType(Enum):
    SD15 = 1
    SDXL = 2
    SD3 = 3
    FLUX = 4


class ComfyuiFaceSwap(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        base_url = self.runtime.credentials.get("base_url", "")
        if not base_url:
            yield self.create_text_message("Please input base_url")
        self.comfyui = ComfyUiClient(base_url)

        images = tool_parameters.get("images") or []
        image_names = []
        for image in images:
            if image.type != FileType.IMAGE:
                continue
            image_name = self.comfyui.upload_image(
                image.filename, image.blob, image.mime_type
            )
            image_names.append(image_name)
        if len(image_names) <= 1:
            raise ToolProviderCredentialValidationError("Please input two images")

        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_dir, "json", "face_swap.json")) as file:
            workflow_json = json.loads(file.read())

        workflow_json["15"]["inputs"]["image"] = image_names[0]
        workflow_json["22"]["inputs"]["image"] = image_names[1]

        try:
            output_images = self.comfyui.generate(workflow_json)
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to generate image: {str(e)}. Maybe install https://github.com/Gourieff/ComfyUI-ReActor on ComfyUI"
            )
        for img in output_images:
            yield self.create_blob_message(
                blob=img["data"],
                meta={
                    "filename": img["filename"],
                    "mime_type": img["mime_type"],
                },
            )

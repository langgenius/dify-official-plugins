import json
import os
from copy import deepcopy
from enum import Enum
from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin import Tool


from tools.comfyui_client import ComfyUiClient, FileType

SD_UPSCALE_OPTIONS = {}


class ModelType(Enum):
    SD15 = 1
    SDXL = 2
    SD3 = 3
    FLUX = 4


class ComfyuiUpscaler(Tool):
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

        if tool_parameters.get("model"):
            self.runtime.credentials["model"] = tool_parameters["model"]
        model = self.runtime.credentials.get("model", None)
        if not model:
            raise ToolProviderCredentialValidationError("Please input model")

        if model not in self.comfyui.get_upscale_models():
            raise ToolProviderCredentialValidationError(f"model {model} does not exist")

        images = tool_parameters.get("images") or []
        image_names = []
        for image in images:
            if image.type != FileType.IMAGE:
                continue
            image_name = self.comfyui.upload_image(
                image.filename, image.blob, image.mime_type
            )
            image_names.append(image_name)
        if len(image_names) == 0:
            raise ToolProviderCredentialValidationError("Please input images")

        if not SD_UPSCALE_OPTIONS:
            current_dir = os.path.dirname(os.path.realpath(__file__))
            with open(os.path.join(current_dir, "json", "upscale.json")) as file:
                SD_UPSCALE_OPTIONS.update(json.load(file))
        workflow_json = deepcopy(SD_UPSCALE_OPTIONS)
        workflow_json["13"]["inputs"]["ckpt_name"] = model
        workflow_json["16"]["inputs"]["image"] = image_name

        try:
            output_images = self.comfyui.generate(workflow_json)
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to generate image: {str(e)}"
            )
        for img in output_images:
            yield self.create_blob_message(
                blob=img["data"],
                meta={
                    "filename": img["filename"],
                    "mime_type": img["mime_type"],
                },
            )

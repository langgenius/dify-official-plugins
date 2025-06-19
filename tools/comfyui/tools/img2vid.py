import json
import os
import random
from copy import deepcopy
from enum import Enum
from typing import Any, Generator
from dify_plugin.entities.tool import (
    ToolInvokeMessage,
)
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin import Tool


from tools.comfyui_client import ComfyUiClient, FileType

SD_TXT2IMG_OPTIONS = {}
LORA_NODE = {
    "inputs": {
        "lora_name": "",
        "strength_model": 1,
        "strength_clip": 1,
        "model": ["11", 0],
        "clip": ["11", 1],
    },
    "class_type": "LoraLoader",
    "_meta": {"title": "Load LoRA"},
}
FluxGuidanceNode = {
    "inputs": {"guidance": 3.5, "conditioning": ["6", 0]},
    "class_type": "FluxGuidance",
    "_meta": {"title": "FluxGuidance"},
}


class ModelType(Enum):
    SD15 = 1
    SDXL = 2
    SD3 = 3
    FLUX = 4


class ComfyuiImg2Vid(Tool):
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

        if model not in self.comfyui.get_checkpoints():
            raise ToolProviderCredentialValidationError(f"model {model} does not exist")
        steps = tool_parameters.get("steps", 20)
        valid_samplers = self.comfyui.get_samplers()
        valid_schedulers = self.comfyui.get_schedulers()
        sampler_name = tool_parameters.get("sampler_name", "euler")
        if sampler_name not in valid_samplers:
            raise ToolProviderCredentialValidationError(
                f"sampler {sampler_name} does not exist"
            )
        scheduler = tool_parameters.get("scheduler", "karras")
        if scheduler not in valid_schedulers:
            raise ToolProviderCredentialValidationError(
                f"scheduler {scheduler} does not exist"
            )
        cfg = tool_parameters.get("cfg", 2.5)
        denoise = tool_parameters.get("denoise", 1.0)
        width = tool_parameters.get("width", 800)
        height = tool_parameters.get("height", 800)
        fps = tool_parameters.get("fps", 6)
        frames = tool_parameters.get("frames", 14)
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
        yield from self.img2vid(
            model=model,
            width=width,
            height=height,
            fps=fps,
            frames=frames,
            denoise=denoise,
            image_name=image_names[0],
            steps=steps,
            sampler_name=sampler_name,
            scheduler=scheduler,
            cfg=cfg,
        )

    def img2vid(
        self,
        model: str,
        width: int,
        height: int,
        fps: int,
        frames: int,
        denoise: float,
        steps: int,
        image_name: str,
        sampler_name: str,
        scheduler: str,
        cfg: float,
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        generate image
        """
        if not SD_TXT2IMG_OPTIONS:
            current_dir = os.path.dirname(os.path.realpath(__file__))
            with open(os.path.join(current_dir, "json", "img2vid.json")) as file:
                SD_TXT2IMG_OPTIONS.update(json.load(file))
        workflow_json = deepcopy(SD_TXT2IMG_OPTIONS)
        workflow_json["3"]["inputs"]["steps"] = steps
        workflow_json["3"]["inputs"]["sampler_name"] = sampler_name
        workflow_json["3"]["inputs"]["scheduler"] = scheduler
        workflow_json["3"]["inputs"]["cfg"] = cfg
        workflow_json["3"]["inputs"]["denoise"] = denoise
        workflow_json["3"]["inputs"]["seed"] = random.randint(0, 100000000)
        workflow_json["12"]["inputs"]["width"] = width
        workflow_json["12"]["inputs"]["height"] = height
        workflow_json["12"]["inputs"]["fps"] = fps
        workflow_json["12"]["inputs"]["video_frames"] = frames
        workflow_json["15"]["inputs"]["ckpt_name"] = model
        workflow_json["23"]["inputs"]["image"] = image_name

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

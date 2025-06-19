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


class ComfyuiImg2Img(Tool):
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
        prompt = tool_parameters.get("prompt", "")
        if not prompt:
            raise ToolProviderCredentialValidationError("Please input prompt")
        negative_prompt = tool_parameters.get("negative_prompt", "")
        steps = tool_parameters.get("steps", 20)
        valid_samplers = self.comfyui.get_samplers()
        valid_schedulers = self.comfyui.get_schedulers()
        sampler_name = tool_parameters.get("sampler_name", "euler")
        if sampler_name not in valid_samplers:
            raise ToolProviderCredentialValidationError(
                f"sampler {sampler_name} does not exist"
            )
        scheduler = tool_parameters.get("scheduler", "normal")
        if scheduler not in valid_schedulers:
            raise ToolProviderCredentialValidationError(
                f"scheduler {scheduler} does not exist"
            )
        cfg = tool_parameters.get("cfg", 7.0)
        denoise = tool_parameters.get("denoise", 0.8)
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

        lora_list = []
        if len(tool_parameters.get("lora_names", "")) > 0:
            lora_list = tool_parameters.get("lora_names").split(",")
        lora_list = [x.lstrip(" ").rstrip(" ") for x in lora_list]
        valid_loras = self.comfyui.get_loras()
        for lora in lora_list:
            if lora not in valid_loras:
                raise ToolProviderCredentialValidationError(
                    f"LORA {lora} does not exist."
                )
        lora_strength_list = []
        if len(tool_parameters.get("lora_strengths", "")) > 0:
            lora_strength_list = [
                float(x.lstrip(" ").rstrip(" "))
                for x in tool_parameters.get("lora_strengths").split(",")
            ]

        yield from self.img2img(
            model=model,
            denoise=denoise,
            prompt=prompt,
            negative_prompt=negative_prompt,
            image_name=image_names[0],
            steps=steps,
            sampler_name=sampler_name,
            scheduler=scheduler,
            cfg=cfg,
            lora_list=lora_list,
            lora_strength_list=lora_strength_list,
        )

    def img2img(
        self,
        model: str,
        denoise: float,
        prompt: str,
        negative_prompt: str,
        steps: int,
        image_name: str,
        sampler_name: str,
        scheduler: str,
        cfg: float,
        lora_list: list[str],
        lora_strength_list: list[float],
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        generate image
        """
        if not SD_TXT2IMG_OPTIONS:
            current_dir = os.path.dirname(os.path.realpath(__file__))
            with open(os.path.join(current_dir, "json", "img2img.json")) as file:
                SD_TXT2IMG_OPTIONS.update(json.load(file))
        workflow_json = deepcopy(SD_TXT2IMG_OPTIONS)
        sampler_node = workflow_json["3"]
        prompt_node = workflow_json["6"]
        negative_prompt_node = workflow_json["7"]
        sampler_node["inputs"]["steps"] = steps
        sampler_node["inputs"]["sampler_name"] = sampler_name
        sampler_node["inputs"]["scheduler"] = scheduler
        sampler_node["inputs"]["cfg"] = cfg
        sampler_node["inputs"]["denoise"] = denoise
        sampler_node["inputs"]["seed"] = random.randint(0, 100000000)
        prompt_node["inputs"]["text"] = prompt
        negative_prompt_node["inputs"]["text"] = negative_prompt

        workflow_json["14"]["inputs"]["ckpt_name"] = model
        workflow_json["10"]["inputs"]["image"] = image_name

        lora_start_id = 100
        lora_end_id = lora_start_id + len(lora_list) - 1
        for i, lora_name in enumerate(lora_list):
            try:
                strength = lora_strength_list[i]
            except:
                strength = 1.0
            lora_node = deepcopy(LORA_NODE)
            lora_node["inputs"]["lora_name"] = lora_name
            lora_node["inputs"]["strength_model"] = strength
            lora_node["inputs"]["strength_clip"] = strength
            lora_node["inputs"]["model"][0] = str(lora_start_id + i - 1)
            lora_node["inputs"]["clip"][0] = str(lora_start_id + i - 1)
            workflow_json[str(lora_start_id + i)] = lora_node
        if len(lora_list) > 0:
            workflow_json[str(lora_start_id)]["inputs"]["model"][0] = sampler_node[
                "inputs"
            ]["model"][0]
            workflow_json[str(lora_start_id)]["inputs"]["clip"][0] = prompt_node[
                "inputs"
            ]["clip"][0]
            sampler_node["inputs"]["model"][0] = str(lora_end_id)
            prompt_node["inputs"]["clip"][0] = str(lora_end_id)
            negative_prompt_node["inputs"]["clip"][0] = str(lora_end_id)

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

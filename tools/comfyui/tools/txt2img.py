import json
import os
import random
import uuid
from copy import deepcopy
from enum import Enum
from typing import Any, Generator
from dify_plugin.entities.tool import (
    ToolInvokeMessage,
    ToolParameter,
    ToolParameterOption,
    I18nObject,
)
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin import Tool

from tools.comfyui_client import ComfyUiClient

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


class ComfyuiTxt2Img(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        base_url = self.runtime.credentials.get("base_url", "")
        if not base_url:
            yield self.create_text_message("Please input base_url")
        self.comfyui = ComfyUiClient(
            base_url,
            self.runtime.credentials.get("comfyui_api_key")
        )
        if tool_parameters.get("model"):
            self.runtime.credentials["model"] = tool_parameters["model"]
        model = self.runtime.credentials.get("model", None)
        if not model:
            yield self.create_text_message("Please input model")
        if model not in self.comfyui.get_checkpoints():
            raise ToolProviderCredentialValidationError(
                f"model {model} does not exist")
        prompt = tool_parameters.get("prompt", "")
        if not prompt:
            yield self.create_text_message("Please input prompt")
        negative_prompt = tool_parameters.get("negative_prompt", "")
        width = tool_parameters.get("width", 1024)
        height = tool_parameters.get("height", 1024)
        steps = tool_parameters.get("steps", 1)
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
        model_type = tool_parameters.get("model_type", ModelType.SD15.name)

        lora_list = []
        if len(tool_parameters.get("lora_names", "")) > 0:
            lora_list = tool_parameters.get("lora_names").split(",")
        valid_loras = self.comfyui.get_loras()
        for lora in lora_list:
            if lora not in valid_loras:
                raise ToolProviderCredentialValidationError(
                    f"LORA {lora} does not exist.")

        lora_strength_list = []
        if len(tool_parameters.get("lora_strengths", "")) > 0:
            lora_strength_list = [float(x) for x in tool_parameters.get(
                "lora_strengths").split(",")]

        yield from self.text2img(
            model=model,
            model_type=model_type,
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            steps=steps,
            sampler_name=sampler_name,
            scheduler=scheduler,
            cfg=cfg,
            lora_list=lora_list,
            lora_strength_list=lora_strength_list,
        )

    def text2img(
        self,
        model: str,
        model_type: str,
        prompt: str,
        negative_prompt: str,
        width: int,
        height: int,
        steps: int,
        sampler_name: str,
        scheduler: str,
        cfg: float,
        lora_list: list,
        lora_strength_list: list,
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        generate image
        """
        if not SD_TXT2IMG_OPTIONS:
            current_dir = os.path.dirname(os.path.realpath(__file__))
            with open(os.path.join(current_dir, "txt2img.json")) as file:
                SD_TXT2IMG_OPTIONS.update(json.load(file))
        draw_options = deepcopy(SD_TXT2IMG_OPTIONS)
        sampler_node = draw_options["3"]
        prompt_node = draw_options["6"]
        negative_prompt_node = draw_options["7"]
        sampler_node["inputs"]["steps"] = steps
        sampler_node["inputs"]["sampler_name"] = sampler_name
        sampler_node["inputs"]["scheduler"] = scheduler
        sampler_node["inputs"]["cfg"] = cfg
        sampler_node["inputs"]["seed"] = random.randint(0, 100000000)
        draw_options["4"]["inputs"]["ckpt_name"] = model
        draw_options["5"]["inputs"]["width"] = width
        draw_options["5"]["inputs"]["height"] = height
        prompt_node["inputs"]["text"] = prompt
        negative_prompt_node["inputs"]["text"] = negative_prompt
        if model_type in {ModelType.SD3.name, ModelType.FLUX.name}:
            draw_options["5"]["class_type"] = "EmptySD3LatentImage"

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
            lora_node["inputs"]["model"][0] = str(lora_start_id+i-1)
            lora_node["inputs"]["clip"][0] = str(lora_start_id+i-1)
            draw_options[str(lora_start_id+i)] = lora_node
        if len(lora_list) > 0:
            draw_options[str(
                lora_start_id)]["inputs"]["model"][0] = sampler_node["inputs"]["model"][0]
            draw_options[str(
                lora_start_id)]["inputs"]["clip"][0] = prompt_node["inputs"]["clip"][0]
            sampler_node["inputs"]["model"][0] = str(lora_end_id)
            prompt_node["inputs"]["clip"][0] = str(lora_end_id)
            negative_prompt_node["inputs"]["clip"][0] = str(lora_end_id)

        if model_type == ModelType.FLUX.name:
            last_node_id = str(10 + len(lora_list))
            draw_options[last_node_id] = deepcopy(FluxGuidanceNode)
            draw_options[last_node_id]["inputs"]["conditioning"][0] = "6"
            draw_options["3"]["inputs"]["positive"][0] = last_node_id
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
            yield self.create_text_message(f"Failed to generate image: {str(e)}")

    def get_runtime_parameters(self) -> list[ToolParameter]:
        parameters = [
            ToolParameter(
                name="prompt",
                label=I18nObject(en_US="Prompt", zh_Hans="Prompt"),
                human_description=I18nObject(
                    en_US="Image prompt, you can check the official documentation of Stable Diffusion",
                    zh_Hans="图像提示词，您可以查看 Stable Diffusion 的官方文档",
                ),
                type=ToolParameter.ToolParameterType.STRING,
                form=ToolParameter.ToolParameterForm.LLM,
                llm_description="Image prompt of Stable Diffusion, you should describe the image you want to generate as a list of words as possible as detailed, the prompt must be written in English.",
                required=True,
            )
        ]
        if self.runtime.credentials:
            try:
                models = self.comfyui.get_checkpoints()
                if len(models) != 0:
                    parameters.append(
                        ToolParameter(
                            name="model",
                            label=I18nObject(en_US="Model", zh_Hans="Model"),
                            human_description=I18nObject(
                                en_US="Model of Stable Diffusion or FLUX, you can check the official documentation of Stable Diffusion or FLUX",
                                zh_Hans="Stable Diffusion 或者 FLUX 的模型，您可以查看 Stable Diffusion 的官方文档",
                            ),
                            type=ToolParameter.ToolParameterType.SELECT,
                            form=ToolParameter.ToolParameterForm.FORM,
                            llm_description="Model of Stable Diffusion or FLUX, you can check the official documentation of Stable Diffusion or FLUX",
                            required=True,
                            default=models[0],
                            options=[
                                ToolParameterOption(
                                    value=i, label=I18nObject(
                                        en_US=i, zh_Hans=i)
                                )
                                for i in models
                            ],
                        )
                    )
                loras = self.comfyui.get_loras()
                if len(loras) != 0:
                    for n in range(1, 4):
                        parameters.append(
                            ToolParameter(
                                name=f"lora_{n}",
                                label=I18nObject(
                                    en_US=f"Lora {n}", zh_Hans=f"Lora {n}"
                                ),
                                human_description=I18nObject(
                                    en_US="Lora of Stable Diffusion, you can check the official documentation of Stable Diffusion",
                                    zh_Hans="Stable Diffusion 的 Lora 模型，您可以查看 Stable Diffusion 的官方文档",
                                ),
                                type=ToolParameter.ToolParameterType.SELECT,
                                form=ToolParameter.ToolParameterForm.FORM,
                                llm_description="Lora of Stable Diffusion, you can check the official documentation of Stable Diffusion",
                                required=False,
                                options=[
                                    ToolParameterOption(
                                        value=i, label=I18nObject(
                                            en_US=i, zh_Hans=i)
                                    )
                                    for i in loras
                                ],
                            )
                        )
                sample_methods = self.comfyui.get_samplers()
                schedulers = self.comfyui.get_schedulers()
                if len(sample_methods) != 0:
                    parameters.append(
                        ToolParameter(
                            name="sampler_name",
                            label=I18nObject(
                                en_US="Sampling method", zh_Hans="Sampling method"
                            ),
                            human_description=I18nObject(
                                en_US="Sampling method of Stable Diffusion, you can check the official documentation of Stable Diffusion",
                                zh_Hans="Stable Diffusion 的Sampling method，您可以查看 Stable Diffusion 的官方文档",
                            ),
                            type=ToolParameter.ToolParameterType.SELECT,
                            form=ToolParameter.ToolParameterForm.FORM,
                            llm_description="Sampling method of Stable Diffusion, you can check the official documentation of Stable Diffusion",
                            required=True,
                            default=sample_methods[0],
                            options=[
                                ToolParameterOption(
                                    value=i, label=I18nObject(
                                        en_US=i, zh_Hans=i)
                                )
                                for i in sample_methods
                            ],
                        )
                    )
                if len(schedulers) != 0:
                    parameters.append(
                        ToolParameter(
                            name="scheduler",
                            label=I18nObject(
                                en_US="Scheduler", zh_Hans="Scheduler"),
                            human_description=I18nObject(
                                en_US="Scheduler of Stable Diffusion, you can check the official documentation of Stable Diffusion",
                                zh_Hans="Stable Diffusion 的Scheduler，您可以查看 Stable Diffusion 的官方文档",
                            ),
                            type=ToolParameter.ToolParameterType.SELECT,
                            form=ToolParameter.ToolParameterForm.FORM,
                            llm_description="Scheduler of Stable Diffusion, you can check the official documentation of Stable Diffusion",
                            required=True,
                            default=schedulers[0],
                            options=[
                                ToolParameterOption(
                                    value=i, label=I18nObject(
                                        en_US=i, zh_Hans=i)
                                )
                                for i in schedulers
                            ],
                        )
                    )
                parameters.append(
                    ToolParameter(
                        name="model_type",
                        label=I18nObject(en_US="Model Type",
                                         zh_Hans="Model Type"),
                        human_description=I18nObject(
                            en_US="Model Type of Stable Diffusion or Flux, you can check the official documentation of Stable Diffusion or Flux",
                            zh_Hans="Stable Diffusion 或 FLUX 的模型类型，您可以查看 Stable Diffusion 或 Flux 的官方文档",
                        ),
                        type=ToolParameter.ToolParameterType.SELECT,
                        form=ToolParameter.ToolParameterForm.FORM,
                        llm_description="Model Type of Stable Diffusion or Flux, you can check the official documentation of Stable Diffusion or Flux",
                        required=True,
                        default=ModelType.SD15.name,
                        options=[
                            ToolParameterOption(
                                value=i, label=I18nObject(en_US=i, zh_Hans=i)
                            )
                            for i in ModelType.__members__
                        ],
                    )
                )
            except:
                pass
        return parameters

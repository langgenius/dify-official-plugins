import json
import os
import random
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
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        base_url = self.runtime.credentials.get("base_url", "")
        if not base_url:
            yield self.create_text_message("Please input base_url")
        self.comfyui = ComfyUiClient(
            base_url, self.runtime.credentials.get("comfyui_api_key")
        )
        if tool_parameters.get("model"):
            self.runtime.credentials["model"] = tool_parameters["model"]
        model = self.runtime.credentials.get("model", None)
        if not model:
            yield self.create_text_message("Please input model")
        if model not in self.comfyui.get_checkpoints():
            raise ToolProviderCredentialValidationError(f"model {model} does not exist")
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
                    f"LORA {lora} does not exist."
                )

        lora_strength_list = []
        if len(tool_parameters.get("lora_strengths", "")) > 0:
            lora_strength_list = [
                float(x) for x in tool_parameters.get("lora_strengths").split(",")
            ]

        # make workflow json
        current_dir = os.path.dirname(os.path.realpath(__file__))
        workflow_template_path = os.path.join(current_dir, "json", "txt2img.json")
        is_hiresfix_enabled: bool = (
            tool_parameters.get("hiresfix_upscale_method") != "disabled"
        )
        if is_hiresfix_enabled:
            workflow_template_path = os.path.join(
                current_dir, "json", "txt2img_hiresfix.json"
            )
        with open(workflow_template_path) as file:
            workflow_json = json.load(file)

        sampler_node = workflow_json["3"]
        prompt_node = workflow_json["6"]
        negative_prompt_node = workflow_json["7"]
        sampler_node["inputs"]["steps"] = steps
        sampler_node["inputs"]["sampler_name"] = sampler_name
        sampler_node["inputs"]["scheduler"] = scheduler
        sampler_node["inputs"]["cfg"] = cfg
        sampler_node["inputs"]["seed"] = random.randint(0, 100000000)
        workflow_json["4"]["inputs"]["ckpt_name"] = model
        workflow_json["5"]["inputs"]["width"] = width
        workflow_json["5"]["inputs"]["height"] = height
        prompt_node["inputs"]["text"] = prompt
        negative_prompt_node["inputs"]["text"] = negative_prompt

        if is_hiresfix_enabled:
            sampler_node2 = workflow_json["11"]
            sampler_node2["inputs"]["sampler_name"] = sampler_name
            sampler_node2["inputs"]["scheduler"] = scheduler
            sampler_node2["inputs"]["steps"] = steps
            sampler_node2["inputs"]["cfg"] = cfg
            sampler_node2["inputs"]["denoise"] = tool_parameters.get(
                "hiresfix_denoise", 0.6
            )

            hiresfix_size_ratio = tool_parameters.get("hiresfix_size_ratio", 0.5)
            workflow_json["5"]["inputs"]["width"] = round(width * hiresfix_size_ratio)
            workflow_json["5"]["inputs"]["height"] = round(height * hiresfix_size_ratio)
            workflow_json["10"]["inputs"]["width"] = width
            workflow_json["10"]["inputs"]["height"] = height
            workflow_json["10"]["inputs"]["upscale_method"] = tool_parameters.get(
                "hiresfix_upscale_method", "bilinear"
            )

        if model_type in {ModelType.SD3.name, ModelType.FLUX.name}:
            workflow_json["5"]["class_type"] = "EmptySD3LatentImage"

        # add loras to workflow json
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

        if model_type == ModelType.FLUX.name:
            last_node_id = str(10 + len(lora_list))
            workflow_json[last_node_id] = deepcopy(FluxGuidanceNode)
            workflow_json[last_node_id]["inputs"]["conditioning"][0] = "6"
            workflow_json["3"]["inputs"]["positive"][0] = last_node_id

        # send a query to ComfyUI
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
        yield self.create_json_message(workflow_json)

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
                                    value=i, label=I18nObject(en_US=i, zh_Hans=i)
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
                                        value=i, label=I18nObject(en_US=i, zh_Hans=i)
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
                                    value=i, label=I18nObject(en_US=i, zh_Hans=i)
                                )
                                for i in sample_methods
                            ],
                        )
                    )
                if len(schedulers) != 0:
                    parameters.append(
                        ToolParameter(
                            name="scheduler",
                            label=I18nObject(en_US="Scheduler", zh_Hans="Scheduler"),
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
                                    value=i, label=I18nObject(en_US=i, zh_Hans=i)
                                )
                                for i in schedulers
                            ],
                        )
                    )
                parameters.append(
                    ToolParameter(
                        name="model_type",
                        label=I18nObject(en_US="Model Type", zh_Hans="Model Type"),
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

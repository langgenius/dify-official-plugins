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
        if tool_parameters.get("model"):
            self.runtime.credentials["model"] = tool_parameters["model"]
        model = self.runtime.credentials.get("model", None)
        if not model:
            yield self.create_text_message("Please input model")
        if model not in self.cli.get_checkpoints():
            raise ToolProviderCredentialValidationError(f"model {model} does not exist")
        prompt = tool_parameters.get("prompt", "")
        if not prompt:
            yield self.create_text_message("Please input prompt")
        negative_prompt = tool_parameters.get("negative_prompt", "")
        width = tool_parameters.get("width", 1024)
        height = tool_parameters.get("height", 1024)
        steps = tool_parameters.get("steps", 1)
        valid_samplers = self.cli.get_samplers()
        valid_schedulers = self.cli.get_schedulers()
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
        lora_strength_list = []
        if tool_parameters.get("lora_1"):
            lora_list.append(tool_parameters["lora_1"])
            lora_strength_list.append(tool_parameters.get("lora_strength_1", 1))
        if tool_parameters.get("lora_2"):
            lora_list.append(tool_parameters["lora_2"])
            lora_strength_list.append(tool_parameters.get("lora_strength_2", 1))
        if tool_parameters.get("lora_3"):
            lora_list.append(tool_parameters["lora_3"])
            lora_strength_list.append(tool_parameters.get("lora_strength_3", 1))
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
        draw_options["3"]["inputs"]["steps"] = steps
        draw_options["3"]["inputs"]["sampler_name"] = sampler_name
        draw_options["3"]["inputs"]["scheduler"] = scheduler
        draw_options["3"]["inputs"]["cfg"] = cfg
        draw_options["3"]["inputs"]["seed"] = random.randint(0, 100000000)
        draw_options["4"]["inputs"]["ckpt_name"] = model
        draw_options["5"]["inputs"]["width"] = width
        draw_options["5"]["inputs"]["height"] = height
        draw_options["6"]["inputs"]["text"] = prompt
        draw_options["7"]["inputs"]["text"] = negative_prompt
        if model_type in {ModelType.SD3.name, ModelType.FLUX.name}:
            draw_options["5"]["class_type"] = "EmptySD3LatentImage"
        if lora_list:
            draw_options["3"]["inputs"]["model"][0] = "10"
            draw_options["6"]["inputs"]["clip"][0] = "10"
            draw_options["7"]["inputs"]["clip"][0] = "10"
            for i, (lora, strength) in enumerate(
                zip(lora_list, lora_strength_list), 10
            ):
                if i - 10 == len(lora_list) - 1:
                    next_node_id = "4"
                else:
                    next_node_id = str(i + 1)
                lora_node = deepcopy(LORA_NODE)
                lora_node["inputs"]["lora_name"] = lora
                lora_node["inputs"]["strength_model"] = strength
                lora_node["inputs"]["strength_clip"] = strength
                lora_node["inputs"]["model"][0] = next_node_id
                lora_node["inputs"]["clip"][0] = next_node_id
                draw_options[str(i)] = lora_node
        if model_type == ModelType.FLUX.name:
            last_node_id = str(10 + len(lora_list))
            draw_options[last_node_id] = deepcopy(FluxGuidanceNode)
            draw_options[last_node_id]["inputs"]["conditioning"][0] = "6"
            draw_options["3"]["inputs"]["positive"][0] = last_node_id
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
                models = self.cli.get_checkpoints()
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
                loras = self.cli.get_loras()
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
                sample_methods = self.cli.get_samplers()
                schedulers = self.cli.get_schedulers()
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

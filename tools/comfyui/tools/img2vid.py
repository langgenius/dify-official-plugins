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
        self.comfyui = ComfyUiClient(
            base_url,
            self.runtime.credentials.get("comfyui_api_key")
        )

        if tool_parameters.get("model"):
            self.runtime.credentials["model"] = tool_parameters["model"]
        model = self.runtime.credentials.get("model", None)
        if not model:
            raise ToolProviderCredentialValidationError(
                "Please input model")

        if model not in self.comfyui.get_checkpoints():
            raise ToolProviderCredentialValidationError(
                f"model {model} does not exist")
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
            image_name = self.comfyui.post_image(
                image.filename, image.blob, image.mime_type)
            image_names.append(image_name)
        if len(image_names) == 0:
            raise ToolProviderCredentialValidationError(
                "Please input images")
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
            with open(os.path.join(current_dir, "img2vid.json")) as file:
                SD_TXT2IMG_OPTIONS.update(json.load(file))
        draw_options = deepcopy(SD_TXT2IMG_OPTIONS)
        draw_options["3"]["inputs"]["steps"] = steps
        draw_options["3"]["inputs"]["sampler_name"] = sampler_name
        draw_options["3"]["inputs"]["scheduler"] = scheduler
        draw_options["3"]["inputs"]["cfg"] = cfg
        draw_options["3"]["inputs"]["denoise"] = denoise
        draw_options["3"]["inputs"]["seed"] = random.randint(0, 100000000)
        draw_options["12"]["inputs"]["width"] = width
        draw_options["12"]["inputs"]["height"] = height
        draw_options["12"]["inputs"]["fps"] = fps
        draw_options["12"]["inputs"]["video_frames"] = frames
        draw_options["15"]["inputs"]["ckpt_name"] = model
        draw_options["23"]["inputs"]["image"] = image_name

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
                meta={"mime_type": "image/webp"},
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

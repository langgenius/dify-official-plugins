import os
import random
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
from tools.comfyui_workflow import ComfyUiWorkflow
from tools.comfyui_client import ComfyUiClient
from tools.model_manager import ModelManager

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
    FLUX1 = 4


class ComfyuiTxt2Img(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        base_url = self.runtime.credentials.get("base_url", "")
        if not base_url:
            yield self.create_text_message("Please input base_url")
        self.comfyui = ComfyUiClient(
            base_url, self.runtime.credentials.get("comfyui_api_key"),
            api_key_comfy_org=self.runtime.credentials.get("api_key_comfy_org")
        )
        self.model_manager = ModelManager(
            self.comfyui,
            civitai_api_key=self.runtime.credentials.get("civitai_api_key"),
            hf_api_key=self.runtime.credentials.get("hf_api_key"),
        )

        model_raw = tool_parameters.get("model", "")
        if model_raw == "":
            model = self.model_manager.download_hugging_face(
                "Comfy-Org/stable-diffusion-v1-5-archive", "v1-5-pruned-emaonly-fp16.safetensors", "checkpoints")
        else:
            model = self.model_manager.decode_model_name(
                model_raw, "checkpoints")

        prompt = tool_parameters.get("prompt", "")
        if not prompt:
            yield self.create_text_message("Please input prompt")
        negative_prompt = tool_parameters.get("negative_prompt", "")
        width = tool_parameters.get("width", 1024)
        height = tool_parameters.get("height", 1024)
        steps = tool_parameters.get("steps", 1)
        valid_samplers = self.comfyui.get_samplers()
        sampler_name = tool_parameters.get("sampler_name", "euler")
        if sampler_name not in valid_samplers:
            raise ToolProviderCredentialValidationError(
                f"Sampler {sampler_name} does not exist. Valid samplers are {valid_samplers}."
            )
        valid_schedulers = self.comfyui.get_schedulers()
        scheduler_name = tool_parameters.get("scheduler", "normal")
        if scheduler_name not in valid_schedulers:
            raise ToolProviderCredentialValidationError(
                f"Scheduler {scheduler_name} does not exist. Valid schedulers are {valid_schedulers}."
            )
        cfg = tool_parameters.get("cfg", 7.0)
        ecosystem = tool_parameters.get("ecosystem", ModelType.SD15.name)

        lora_list = []
        try:
            for lora_info in tool_parameters.get("loras", "").split(","):
                lora_info = lora_info.lstrip(" ").rstrip(" ")
                if lora_info == "":
                    continue
                lora_list.append(
                    self.model_manager.decode_lora(lora_info)
                )
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))

        lora_strength_list = []
        if len(tool_parameters.get("lora_strengths", "")) > 0:
            lora_strength_list = [
                float(x) for x in tool_parameters.get("lora_strengths").split(",")
            ]
        batch_size = int(tool_parameters.get("batch_size", 1))

        # make workflow json
        current_dir = os.path.dirname(os.path.realpath(__file__))
        workflow_template_path = os.path.join(
            current_dir, "json", "txt2img.json")
        is_hiresfix_enabled: bool = (
            tool_parameters.get("hiresfix_upscale_method") != "disabled"
        )
        if is_hiresfix_enabled:
            workflow_template_path = os.path.join(
                current_dir, "json", "txt2img_hiresfix.json"
            )
        with open(workflow_template_path) as file:
            workflow = ComfyUiWorkflow(file.read())

        workflow.set_Ksampler(
            "3",
            steps,
            sampler_name,
            scheduler_name,
            cfg,
            1.0,
            random.randint(0, 100000000),
        )
        workflow.set_model_loader(None, model)
        workflow.set_property("6", "inputs/text", prompt)
        workflow.set_property("7", "inputs/text", negative_prompt)

        if is_hiresfix_enabled:
            workflow.set_Ksampler(
                "11",
                steps,
                sampler_name,
                scheduler_name,
                cfg,
                tool_parameters.get("hiresfix_denoise", 0.6),
                random.randint(0, 100000000),
            )

            hiresfix_size_ratio = tool_parameters.get(
                "hiresfix_size_ratio", 0.5)
            workflow.set_empty_latent_image(
                workflow.identify_node_by_class_type("EmptyLatentImage"),
                round(width * hiresfix_size_ratio),
                round(height * hiresfix_size_ratio),
                batch_size
            )

            workflow.set_property("10", "inputs/width", width)
            workflow.set_property("10", "inputs/height", height)
            workflow.set_property(
                "10",
                "inputs/upscale_method",
                tool_parameters.get("hiresfix_upscale_method", "bilinear"),
            )
        else:
            workflow.set_empty_latent_image(None, width, height, batch_size)

        if ecosystem in {ModelType.SD3.name, ModelType.FLUX1.name}:
            workflow.set_property("5", "class_type", "EmptySD3LatentImage")

        # add loras to workflow json
        for i, lora_info in enumerate(lora_list):
            try:
                strength = lora_strength_list[i]
            except:
                strength = 1.0
            workflow.add_lora_node(
                "3", "6", "7", lora_info, strength, strength)

        if ecosystem == ModelType.FLUX1.name:
            workflow.add_flux_guidance("3", 3.5)

        # send a query to ComfyUI
        try:
            output_images = self.comfyui.generate(workflow.json())
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to generate image: {str(e)}"
            )
        for img in output_images:
            yield self.create_blob_message(
                blob=img.blob,
                meta={
                    "filename": img.filename,
                    "mime_type": img.mime_type,
                },
            )
        yield self.create_json_message(workflow.json())

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

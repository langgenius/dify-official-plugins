import os
import random
from enum import Enum
from typing import Any, Generator
from dify_plugin.entities.tool import (
    ToolInvokeMessage,
)
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin import Tool
from tools.comfyui_workflow import ComfyUiWorkflow
from tools.comfyui_client import ComfyUiClient, FileType
from tools.model_manager import ModelManager


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
        self.comfyui = ComfyUiClient(
            base_url, api_key_comfy_org=self.runtime.credentials.get("api_key_comfy_org"))
        self.model_manager = ModelManager(
            self.comfyui,
            civitai_api_key=self.runtime.credentials.get("civitai_api_key"),
            hf_api_key=self.runtime.credentials.get("hf_api_key"),
        )

        model_raw = tool_parameters.get("model", "")
        if model_raw == "":
            model = self.model_manager.download_hugging_face(
                "Comfy-Org/stable-diffusion-v1-5-archive",
                "v1-5-pruned-emaonly-fp16.safetensors",
                "checkpoints",
            )
        else:
            model = self.model_manager.decode_model_name(
                model_raw, "checkpoints")

        prompt = tool_parameters.get("prompt", "")
        if not prompt:
            raise ToolProviderCredentialValidationError("Please input prompt")
        negative_prompt = tool_parameters.get("negative_prompt", "")
        steps = tool_parameters.get("steps", 20)

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
        batch_size = int(tool_parameters.get("batch_size", 1))

        lora_strength_list = []
        if len(tool_parameters.get("lora_strengths", "")) > 0:
            lora_strength_list = [
                float(x.lstrip(" ").rstrip(" "))
                for x in tool_parameters.get("lora_strengths").split(",")
            ]

        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_dir, "json", "img2img.json")) as file:
            workflow = ComfyUiWorkflow(file.read())
        workflow.set_Ksampler(
            None,
            steps,
            sampler_name,
            scheduler_name,
            cfg,
            denoise,
            random.randint(0, 100000000),
        )
        workflow.set_prompt("6", prompt)
        workflow.set_prompt("7", negative_prompt)
        workflow.set_model_loader(None, model)
        workflow.set_image_names([image_name])

        for i, lora_name in enumerate(lora_list):
            try:
                strength = lora_strength_list[i]
            except:
                strength = 1.0
            workflow.add_lora_node(
                "3", "6", "7", lora_name, strength, strength)

        for _ in range(batch_size):
            workflow.randomize_seed()
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

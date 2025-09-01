import dataclasses
import json
import os
import random
from typing import Any, Generator
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from tools.comfyui_workflow import ComfyUiWorkflow
from tools.comfyui_client import ComfyUiClient, FileType
from tools.model_manager import ModelManager


@dataclasses.dataclass
class QuickStartConfig:
    image_names: list[str]
    prompt: str | None
    negative_prompt: str | None
    width: int | None
    height: int | None
    lora_names: list[str]
    lora_strengths: list[float]
    feature: str


class QuickStart(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        base_url = self.runtime.credentials.get("base_url")
        if base_url is None:
            yield self.create_text_message("Please input base_url")
        self.comfyui = ComfyUiClient(
            base_url, self.runtime.credentials.get("comfyui_api_key")
        )
        self.model_manager = ModelManager(
            self.comfyui,
            civitai_api_key=self.runtime.credentials.get("civitai_api_key"),
            hf_api_key=self.runtime.credentials.get("hf_api_key"),
        )
        image_names = []
        for image in tool_parameters.get("images", []):
            if image.type != FileType.IMAGE:
                continue
            image_name = self.comfyui.upload_image(
                image.filename, image.blob, image.mime_type
            )
            image_names.append(image_name)
        lora_names = []
        lora_strengths = []
        try:
            loras: str = tool_parameters.get("loras", "")
            for lora_info in loras.split(","):
                if lora_info == "":
                    continue
                lora_name, lora_strength = self.model_manager.decode_lora(
                    lora_info)
                lora_names.append(lora_name)
                lora_strengths.append(lora_strength)
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))

        ui = QuickStartConfig(image_names=image_names,
                              prompt=tool_parameters.get("prompt"),
                              negative_prompt=tool_parameters.get(
                                  "negative_prompt"),
                              width=tool_parameters.get("width"),
                              height=tool_parameters.get("height"),
                              lora_names=lora_names,
                              lora_strengths=lora_strengths,
                              feature=tool_parameters.get("feature"))

        workflow = ""
        output_images = []
        if ui.feature == "qwen_image":
            workflow, output_images = self.qwen_image(ui)
        elif ui.feature == "qwen_image_edit":
            workflow, output_images = self.qwen_image_edit(ui)
        elif ui.feature == "flux_dev_fp8":
            workflow, output_images = self.flux_dev_fp8(ui)
        elif ui.feature == "flux_schnell_fp8":
            workflow, output_images = self.flux_schnell_fp8(ui)
        elif ui.feature == "pony_v6_xl":
            # The highest rated and most liked model on https://civitai.com/models so far.
            workflow, output_images = self.pony_v6_xl(ui)
        elif ui.feature == "majicmix_realistic":
            # the most liked SD1.5-based model on CivitAI
            workflow, output_images = self.majicmix_realistic(ui)
        elif ui.feature == "wai_illustrious":
            # the most liked Illustrious-based model on CivitAI
            workflow, output_images = self.wai_illustrious(ui)

        yield self.create_text_message(workflow)
        for img in output_images:
            yield self.create_blob_message(
                blob=img.blob,
                meta={
                    "filename": img.filename,
                    "mime_type": img.mime_type,
                },
            )

    def qwen_image(self, ui: QuickStartConfig):
        models = [
            {
                "name": "qwen_image_fp8_e4m3fn.safetensors",
                "url": "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_fp8_e4m3fn.safetensors",
                "directory": "diffusion_models"
            },
            {
                "name": "qwen_image_vae.safetensors",
                "url": "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors",
                "directory": "vae"
            },
            {
                "name": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
                "url": "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors",
                "directory": "text_encoders"
            },
            {
                "name": "Qwen-Image-Lightning-8steps-V1.0.safetensors",
                "url": "https://huggingface.co/lightx2v/Qwen-Image-Lightning/resolve/main/Qwen-Image-Lightning-8steps-V1.0.safetensors",
                "directory": "loras"
            }
        ]
        for model in models:
            self.model_manager.download_model(model["url"], model["directory"])

        current_dir = os.path.dirname(os.path.realpath(__file__))
        current_dir = os.path.dirname(os.path.realpath(__file__))
        filepath = os.path.join(current_dir, "json", "qwen_image.json")
        with open(filepath, "r", encoding="utf-8") as f:
            workflow = ComfyUiWorkflow(json.load(f))

        workflow.set_prompt("6", ui.prompt)
        workflow.set_prompt("7", ui.negative_prompt)
        if ui.width is None or ui.height is None:
            raise ToolProviderCredentialValidationError(
                "Please input width and height")
        workflow.set_SD3_latent_image(None, ui.width, ui.height)
        workflow.set_Ksampler(None, 8, "euler", "simple",
                              2.5, 1.0, random.randint(0, 10**8))
        for i, lora_name in enumerate(ui.lora_names):
            workflow.add_lora_node(
                "3", "6", "7", lora_name, ui.lora_strengths[i])

        output_images = self.comfyui.generate(workflow.json())
        return workflow.json_str(), output_images

    def qwen_image_edit(self, ui: QuickStartConfig):
        models = [
            {
                "name": "qwen_image_edit_fp8_e4m3fn.safetensors",
                "url": "https://huggingface.co/Comfy-Org/Qwen-Image-Edit_ComfyUI/resolve/main/split_files/diffusion_models/qwen_image_edit_fp8_e4m3fn.safetensors",
                "directory": "diffusion_models"
            },
            {
                "name": "qwen_image_vae.safetensors",
                "url": "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/vae/qwen_image_vae.safetensors",
                "directory": "vae"
            },
            {
                "name": "qwen_2.5_vl_7b_fp8_scaled.safetensors",
                "url": "https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/main/split_files/text_encoders/qwen_2.5_vl_7b_fp8_scaled.safetensors",
                "directory": "text_encoders"
            },
            {
                "name": "Qwen-Image-Lightning-4steps-V1.0.safetensors",
                "url": "https://huggingface.co/lightx2v/Qwen-Image-Lightning/resolve/main/Qwen-Image-Lightning-4steps-V1.0.safetensors",
                "directory": "loras"
            }
        ]
        for model in models:
            self.model_manager.download_model(model["url"], model["directory"])

        if len(ui.image_names) == 0:
            raise ToolProviderCredentialValidationError(
                "Please input an image")

        current_dir = os.path.dirname(os.path.realpath(__file__))
        filepath = os.path.join(current_dir, "json", "qwen_image_edit.json")
        with open(filepath, "r", encoding="utf-8") as f:
            workflow = ComfyUiWorkflow(json.load(f))

        workflow.set_property("76", "inputs/prompt", ui.prompt)
        workflow.set_property("77", "inputs/prompt", ui.negative_prompt)
        workflow.set_image_names(ui.image_names)
        workflow.set_Ksampler(None, 4, "euler", "simple",
                              1.0, 1.0, random.randint(0, 10**8))

        output_images = self.comfyui.generate(workflow.json())
        return workflow.json_str(), output_images

    def flux_dev_fp8(self, ui: QuickStartConfig):
        models = [
            {
                "name": "flux1-dev-fp8.safetensors",
                "url": "https://huggingface.co/Comfy-Org/flux1-dev/resolve/main/flux1-dev-fp8.safetensors?download=true",
                "directory": "checkpoints"
            }
        ]
        for model in models:
            self.model_manager.download_model(model["url"], model["directory"])

        current_dir = os.path.dirname(os.path.realpath(__file__))
        filepath = os.path.join(current_dir, "json", "flux_dev_fp8.json")
        with open(filepath, "r", encoding="utf-8") as f:
            workflow = ComfyUiWorkflow(json.load(f))

        workflow.set_prompt("6", ui.prompt)
        workflow.set_prompt("33", ui.negative_prompt)
        workflow.set_Ksampler(None, 20, "euler", "simple",
                              1.0, 1.0, random.randint(0, 10**8))
        for i, lora_name in enumerate(ui.lora_names):
            workflow.add_lora_node(
                "31", "6", "33", lora_name, ui.lora_strengths[i])

        output_images = self.comfyui.generate(workflow.json())
        return workflow.json_str(), output_images

    def flux_schnell_fp8(self, ui: QuickStartConfig):
        models = [
            {
                "name": "flux1-schnell-fp8.safetensors",
                "url": "https://huggingface.co/Comfy-Org/flux1-schnell/resolve/main/flux1-schnell-fp8.safetensors?download=true",
                "directory": "checkpoints"
            }
        ]
        for model in models:
            self.model_manager.download_model(model["url"], model["directory"])

        current_dir = os.path.dirname(os.path.realpath(__file__))
        filepath = os.path.join(current_dir, "json", "flux_schnell_fp8.json")
        with open(filepath, "r", encoding="utf-8") as f:
            workflow = ComfyUiWorkflow(json.load(f))

        workflow.set_prompt("6", ui.prompt)
        workflow.set_prompt("33", ui.negative_prompt)
        workflow.set_Ksampler(None, 4, "euler", "simple",
                              1.0, 1.0, random.randint(0, 10**8))
        for i, lora_name in enumerate(ui.lora_names):
            workflow.add_lora_node(
                "31", "6", "33", lora_name, ui.lora_strengths[i])

        output_images = self.comfyui.generate(workflow.json())
        return workflow.json_str(), output_images

    def get_civitai_workflow(self, ui: QuickStartConfig) -> ComfyUiWorkflow:
        current_dir = os.path.dirname(os.path.realpath(__file__))
        filepath = os.path.join(current_dir, "json", "txt2img.json")
        with open(filepath, "r", encoding="utf-8") as f:
            workflow = ComfyUiWorkflow(json.load(f))

        workflow.set_prompt("6", ui.prompt)
        workflow.set_prompt("7", ui.negative_prompt)
        for i, lora_name in enumerate(ui.lora_names):
            workflow.add_lora_node(
                "3", "6", "7", lora_name, ui.lora_strengths[i])
        workflow.set_empty_latent_image(None, ui.width, ui.height)
        return workflow

    def pony_v6_xl(self, ui: QuickStartConfig):
        model_name_human, filenames = self.model_manager.download_civitai(
            257749, 290640, "checkpoints")
        workflow = self.get_civitai_workflow(ui)
        workflow.set_model_loader(None, filenames[0])
        workflow.set_Ksampler(None, 25, "euler_ancestral",
                              "normal", 8.5, 1.0, random.randint(0, 10**8))
        output_images = self.comfyui.generate(workflow.json())
        return workflow.json_str(), output_images

    def majicmix_realistic(self, ui: QuickStartConfig):
        model_name_human, filenames = self.model_manager.download_civitai(
            43331, 176425, "checkpoints")
        workflow = self.get_civitai_workflow(ui)
        workflow.set_model_loader(None, filenames[0])
        workflow.set_Ksampler(None, 30, "euler_ancestral",
                              "normal", 8.5, 1.0, random.randint(0, 10**8))

        output_images = self.comfyui.generate(workflow.json())
        return workflow.json_str(), output_images

    def wai_illustrious(self, ui: QuickStartConfig):
        model_name_human, filenames = self.model_manager.download_civitai(
            827184, 1761560, "checkpoints")

        workflow = self.get_civitai_workflow(ui)
        workflow.set_model_loader(None, filenames[0])
        workflow.set_Ksampler(None, 30, "euler_ancestral",
                              "normal", 6.0, 1.0, random.randint(0, 10**8))

        output_images = self.comfyui.generate(workflow.json())
        return workflow.json_str(), output_images

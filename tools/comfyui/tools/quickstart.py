import os
from typing import Any, Generator
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from tools.comfyui_workflow import ComfyUiWorkflow
from tools.comfyui_client import ComfyUiClient, FileType
from tools.model_manager import ModelManager


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

        feature: str = tool_parameters.get("feature")
        prompt: str = tool_parameters.get("prompt", "")
        negative_prompt: str = tool_parameters.get("negative_prompt", "")
        images = tool_parameters.get("images", [])
        image_names = []
        for image in images:
            if image.type != FileType.IMAGE:
                continue
            image_name = self.comfyui.upload_image(
                image.filename, image.blob, image.mime_type
            )
            image_names.append(image_name)

        output_images = []
        if feature == "qwen_image_edit":
            output_images = self.qwen_image_edit(
                prompt, negative_prompt, image_names)
        elif feature == "flux_schnell_fp8":
            output_images = self.flux_schnell_fp8(
                prompt, negative_prompt)

        for img in output_images:
            yield self.create_blob_message(
                blob=img["data"],
                meta={
                    "filename": img["filename"],
                    "mime_type": img["mime_type"],
                },
            )

    def qwen_image_edit(self, prompt: str, negative_prompt: str, image_names: list[str]):
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
            }, {
                "name": "Qwen-Image-Lightning-8steps-V1.0.safetensors",
                "url": "https://huggingface.co/lightx2v/Qwen-Image-Lightning/resolve/main/Qwen-Image-Lightning-8steps-V1.0.safetensors",
                "directory": "loras"
            }
        ]
        for model in models:
            self.model_manager.download_model(model["url"], model["directory"])

        current_dir = os.path.dirname(os.path.realpath(__file__))
        workflow = ComfyUiWorkflow()
        workflow.load_from_file(os.path.join(current_dir, "json", "qwen.json"))
        workflow.set_prompt("6", prompt)
        workflow.set_prompt("7", negative_prompt)
        workflow.set_image_names(image_names)

        output_images = self.comfyui.generate(workflow.json())
        return output_images

    def flux_schnell_fp8(self, prompt: str, negative_prompt: str):
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
        workflow = ComfyUiWorkflow()
        workflow.load_from_file(os.path.join(
            current_dir, "json", "flux_schnell_fp8.json"))
        workflow.set_prompt("6", prompt)
        workflow.set_prompt("33", negative_prompt)
        output_images = self.comfyui.generate(workflow.json())
        return output_images

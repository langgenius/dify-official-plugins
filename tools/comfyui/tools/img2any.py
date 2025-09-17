import os
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from tools.comfyui_client import ComfyUiClient, ComfyUiFile, FileType
from tools.comfyui_model_manager import ModelManager
from tools.comfyui_workflow import ComfyUiWorkflow


class ComfyuiImg2Any(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        self.comfyui = ComfyUiClient(
            base_url=self.runtime.credentials.get("base_url"),
            api_key=self.runtime.credentials.get("comfyui_api_key"),
            api_key_comfy_org=self.runtime.credentials.get("api_key_comfy_org"),
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
            image_name = self.comfyui.upload_image(image.filename, image.blob, image.mime_type)
            image_names.append(image_name)

        output_images = []
        if feature.startswith("depth_anything_"):
            output_images = self.depth_anything(feature, image_names)
        elif feature.startswith("depth_pro"):
            output_images = self.depth_pro(feature, image_names)
        elif feature == "face_swap":
            output_images = self.face_swap(image_names[0], image_names[1])
        elif feature.startswith("upscale"):
            output_images = self.upscale(feature, image_names)

        for img in output_images:
            yield self.create_blob_message(
                blob=img.blob,
                meta={
                    "filename": img.filename,
                    "mime_type": img.mime_type,
                },
            )

    def depth_pro(self, feature, image_names) -> list[ComfyUiFile]:
        output_images = []
        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_dir, "json", "depth_pro.json")) as file:
            workflow = ComfyUiWorkflow(file.read())
        precision = "fp16"
        if "fp32" in feature:
            precision = "fp32"
        workflow.set_property("6", "inputs/precision", precision)

        for image_name in image_names:
            workflow.set_property("8", "inputs/image", image_name)
            try:
                output_images.append(self.comfyui.generate(workflow.json())[0])
            except Exception as e:
                raise ToolProviderCredentialValidationError(
                    f"Failed to generate image: {str(e)}."
                    + " Maybe install https://github.com/spacepxl/ComfyUI-Depth-Pro on ComfyUI"
                )
        return output_images

    def depth_anything(self, feature, image_names) -> list[ComfyUiFile]:
        output_images = []
        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_dir, "json", "depth_anything.json")) as file:
            workflow = ComfyUiWorkflow(file.read())
        workflow.set_property("2", "inputs/model", feature)
        for image_name in image_names:
            workflow.set_property("3", "inputs/image", image_name)
            try:
                output_images.append(self.comfyui.generate(workflow.json())[0])
            except Exception as e:
                raise ToolProviderCredentialValidationError(
                    f"Failed to generate image: {str(e)}."
                    + " Maybe install https://github.com/kijai/ComfyUI-DepthAnythingV2 on ComfyUI"
                )
        return output_images

    def face_swap(self, image_name1, image_name2) -> list[ComfyUiFile]:
        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_dir, "json", "face_swap.json")) as file:
            workflow = ComfyUiWorkflow(file.read())
        workflow.set_property("15", "inputs/image", image_name1)
        workflow.set_property("22", "inputs/image", image_name2)
        try:
            output_images = self.comfyui.generate(workflow.json())
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to generate image: {str(e)}."
                + " Maybe install https://github.com/Gourieff/ComfyUI-ReActor on ComfyUI"
            )
        return output_images

    def upscale(self, feature, image_names) -> list[ComfyUiFile]:
        output_images = []
        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_dir, "json", "upscale.json")) as file:
            workflow = ComfyUiWorkflow(file.read())
        if "esrgan" in feature:
            model_name = self.model_manager.download_model(
                "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
                "upscale_models",
            )
        workflow.set_property("13", "inputs/model_name", model_name)
        for image_name in image_names:
            workflow.set_property("16", "inputs/image", image_name)
            try:
                output_images.append(self.comfyui.generate(workflow.json())[0])
            except Exception as e:
                raise ToolProviderCredentialValidationError(
                    f"Failed to generate image: {str(e)}."
                    + " Maybe install https://github.com/kijai/ComfyUI-DepthAnythingV2 on ComfyUI"
                )
        return output_images

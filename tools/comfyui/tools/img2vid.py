import dataclasses
import io
import os
import random
from enum import Enum
from typing import Any, Generator
from dify_plugin.entities.tool import (
    ToolInvokeMessage,
)
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin import Tool
from PIL import Image
from tools.comfyui_client import ComfyUiClient, FileType
from tools.comfyui_workflow import ComfyUiWorkflow
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


@dataclasses.dataclass(frozen=False)
class ComfyuiImg2VidConfig:
    model_name: str
    width: int
    height: int
    fps: int
    frameN: int
    denoise: float
    image_name: str
    steps: int
    sampler_name: str
    scheduler_name: str
    cfg: float
    output_format: str
    memory_usage: str
    prompt: str | None
    negative_prompt: str | None


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
        self.comfyui = ComfyUiClient(base_url)

        steps = tool_parameters.get("steps", 20)
        denoise = tool_parameters.get("denoise", 1.0)
        cfg = tool_parameters.get("cfg", 3.5)
        valid_samplers = self.comfyui.get_samplers()
        sampler_name = tool_parameters.get("sampler_name")
        if sampler_name is None or sampler_name == "":
            sampler_name = "euler"
        if sampler_name not in valid_samplers:
            raise ToolProviderCredentialValidationError(
                f"Sampler {sampler_name} does not exist. Valid samplers are {valid_samplers}."
            )
        valid_schedulers = self.comfyui.get_schedulers()
        scheduler_name = tool_parameters.get("scheduler")
        if scheduler_name is None or scheduler_name == "":
            scheduler_name = "normal"
        if scheduler_name not in valid_schedulers:
            raise ToolProviderCredentialValidationError(
                f"Scheduler {scheduler_name} does not exist. Valid schedulers are {valid_schedulers}."
            )
        fps = tool_parameters.get("fps", 6)
        frameN = tool_parameters.get("frameN", 14)
        images = tool_parameters.get("images") or []
        image = None
        for file in images:
            if file.type != FileType.IMAGE:
                continue
            image = file
            break
        if image is None:
            raise ToolProviderCredentialValidationError("Please input images")

        image_name = self.comfyui.upload_image(
            image.filename, image.blob, image.mime_type
        )
        pil_img = Image.open(io.BytesIO(image.blob))
        width = pil_img.width
        height = pil_img.height

        config = ComfyuiImg2VidConfig(
            model_name=tool_parameters.get("model_name", ""),
            width=width,
            height=height,
            fps=fps,
            frameN=frameN,
            denoise=denoise,
            cfg=cfg,
            image_name=image_name,
            steps=steps,
            sampler_name=sampler_name,
            scheduler_name=scheduler_name,
            output_format=tool_parameters.get("output_format", "mp4"),
            memory_usage=tool_parameters.get("memory_usage"),
            prompt=tool_parameters.get("prompt", ""),
            negative_prompt=tool_parameters.get("negative_prompt", ""),
        )

        model_type = tool_parameters.get("model_type")
        if model_type == "wan2_1":
            output_images = self.img2vid_svd_wan2_1(config)
        elif model_type == "ltxv":
            output_images = self.img2vid_ltxv(config)
        elif model_type == "svd":
            output_images = self.img2vid_svd(config)
        elif model_type == "svd_xt":
            config.model_name = self.comfyui.download_model(
                "https://huggingface.co/stabilityai/stable-video-diffusion-img2vid-xt/resolve/main/svd_xt.safetensors",
                "checkpoints",
                token=self.get_hf_key(),
            )
            output_images = self.img2vid_svd(config)

        for img in output_images:
            if config.output_format == "mp4":
                img = self.comfyui.convert_webp2mp4(img["data"], config.fps)
            yield self.create_blob_message(
                blob=img["data"],
                meta={
                    "filename": img["filename"],
                    "mime_type": img["mime_type"],
                },
            )

    def get_civit_key(self) -> str:
        civitai_api_key = self.runtime.credentials.get("civitai_api_key")
        if civitai_api_key is None:
            raise ToolProviderCredentialValidationError(
                "Please input civitai_api_key")
        return civitai_api_key

    def get_hf_key(self) -> str:
        hf_api_key = self.runtime.credentials.get("hf_api_key")
        if hf_api_key is None:
            raise ToolProviderCredentialValidationError(
                "Please input hf_api_key")
        return hf_api_key

    def img2vid_svd(
        self, config: ComfyuiImg2VidConfig
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        generate image
        """
        if config.model_name == "":
            # download model
            config.model_name = self.comfyui.download_model(
                "https://huggingface.co/stabilityai/stable-video-diffusion-img2vid/resolve/main/svd.safetensors",
                "checkpoints",
                token=self.get_hf_key(),
            )

        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_dir, "json", "img2vid_svd.json")) as file:
            workflow = ComfyUiWorkflow(file.read())
        workflow.set_Ksampler(None, config.steps, config.sampler_name, config.scheduler_name,
                              config.cfg, config.denoise, random.randint(0, 100000000))
        workflow.set_animated_webp(None, config.fps)
        workflow.set_property("12", "inputs/width", config.width)
        workflow.set_property("12", "inputs/height", config.height)
        workflow.set_property("12", "inputs/fps", config.fps)
        workflow.set_property("12", "inputs/video_frames", config.frameN)
        workflow.set_property("15", "inputs/ckpt_name", config.model_name)
        workflow.set_image_names([config.image_name])

        try:
            output_images = self.comfyui.generate(workflow.json())
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to generate image: {str(e)}"
            )
        return output_images

    def img2vid_svd_wan2_1(
        self, config: ComfyuiImg2VidConfig
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        generate image
        """
        if config.model_name == "":
            # download model
            config.model_name = self.comfyui.download_model(
                "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/diffusion_models/wan2.1_i2v_480p_14B_fp8_e4m3fn.safetensors",
                "diffusion_models",
                token=self.get_hf_key(),
            )

        vae = self.comfyui.download_model(
            "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/vae/wan_2.1_vae.safetensors",
            "vae",
            token=self.get_hf_key(),
        )
        clip_vision = self.comfyui.download_model(
            "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/clip_vision/clip_vision_h.safetensors",
            "clip_vision",
            token=self.get_hf_key(),
        )
        text_encoder = self.comfyui.download_model(
            "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
            "text_encoders",
            token=self.get_hf_key(),
        )
        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_dir, "json", "img2vid_wan2_1.json")) as file:
            workflow = ComfyUiWorkflow(file.read())
        workflow.set_Ksampler(None, config.steps, config.sampler_name, config.scheduler_name,
                              config.cfg, config.denoise, random.randint(0, 100000000))
        workflow.set_property("50", "inputs/width", config.width)
        workflow.set_property("50", "inputs/height", config.height)
        workflow.set_property("50", "inputs/length", config.frameN)
        workflow.set_prompt("6", config.prompt)
        workflow.set_prompt("7", config.negative_prompt)
        workflow.set_animated_webp(None, config.fps)
        workflow.set_unet(None, config.model_name)
        workflow.set_clip(None, text_encoder)
        workflow.set_vae(None, vae)
        workflow.set_clip_vision(None, clip_vision)
        workflow.set_image_names([config.image_name])

        try:
            output_images = self.comfyui.generate(workflow.json())
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to generate image: {str(e)}"
            )
        return output_images

    def img2vid_ltxv(
        self, config: ComfyuiImg2VidConfig
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        generate image
        """
        if config.frameN < 10:
            raise ToolProviderCredentialValidationError(
                "FrameN must be 10 or more for LTXV"
            )
        if config.model_name == "":
            # download model
            config.model_name = self.comfyui.download_model(
                "https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltx-video-2b-v0.9.safetensors",
                "checkpoints",
                token=self.get_hf_key(),
            )
        text_encoder = self.comfyui.download_model(
            "https://huggingface.co/comfyanonymous/flux_text_encoders/resolve/main/t5xxl_fp16.safetensors",
            "text_encoders",
            token=self.get_hf_key(),
        )

        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_dir, "json", "img2vid_ltxv.json")) as file:
            workflow = ComfyUiWorkflow(file.read())
        workflow.set_property("77", "inputs/width", config.width)
        workflow.set_property("77", "inputs/height", config.height)
        workflow.set_property("77", "inputs/length", config.frameN)
        workflow.set_clip(None, text_encoder)
        workflow.set_animated_webp(None, config.fps)
        workflow.set_property("69", "inputs/frame_rate", config.fps)
        workflow.set_property("72", "inputs/noise_seed",
                              random.randint(0, 100000000))
        workflow.set_image_names([config.image_name])
        workflow.set_prompt("6", config.prompt)
        workflow.set_prompt("7", config.negative_prompt)

        try:
            output_images = self.comfyui.generate(workflow.json())
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to generate image: {str(e)}"
            )
        return output_images

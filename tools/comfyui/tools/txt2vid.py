import dataclasses
import os
import random
from typing import Any, Generator
from dify_plugin.entities.tool import (
    ToolInvokeMessage,
)
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin import Tool
from tools.comfyui_client import ComfyUiClient
from tools.comfyui_workflow import ComfyUiWorkflow
from tools.model_manager import ModelManager


@dataclasses.dataclass(frozen=False)
class ComfyuiTxt2VidConfig:
    model_name: str
    prompt: str
    negative_prompt: str
    width: int
    height: int
    fps: int
    frameN: int
    steps: int
    sampler_name: str
    scheduler_name: str
    cfg: float
    output_format: str
    memory_usage: str


class ComfyuiTxt2Vid(Tool):
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
            api_key_comfy_org=self.runtime.credentials.get(
                "api_key_comfy_org"),
        )
        self.model_manager = ModelManager(
            self.comfyui,
            civitai_api_key=self.runtime.credentials.get("civitai_api_key"),
            hf_api_key=self.runtime.credentials.get("hf_api_key"),
        )

        steps = tool_parameters.get("steps", 20)
        width = tool_parameters.get("width")
        height = tool_parameters.get("height")
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

        config = ComfyuiTxt2VidConfig(
            model_name="",
            prompt=tool_parameters.get("prompt", ""),
            negative_prompt=tool_parameters.get("negative_prompt", ""),
            width=width,
            height=height,
            fps=fps,
            frameN=frameN,
            cfg=cfg,
            steps=steps,
            sampler_name=sampler_name,
            scheduler_name=scheduler_name,
            output_format=tool_parameters.get("output_format", "mp4"),
            memory_usage=tool_parameters.get("memory_usage"),
        )

        model_type = tool_parameters.get("model_type")

        output_images = []
        if model_type == "wan2_1":
            output_images = self.txt2vid_wan2_1(config)
        elif model_type == "wan2_2_5B":
            output_images = self.txt2vid_wan2_2_5B(config)
        elif model_type == "wan2_2_14B":
            output_images = self.txt2vid_wan2_2_14B(config)
        elif model_type == "ltxv":
            output_images = self.txt2vid_ltxv(config)
        elif model_type == "mochi":
            output_images = self.txt2vid_mochi(config)
        elif model_type == "hunyuan":
            output_images = self.txt2vid_hunyuan(config)

        for img in output_images:
            if config.output_format == "mp4":
                img = self.comfyui.convert_webp2mp4(img.blob, config.fps)
            yield self.create_blob_message(
                blob=img.blob,
                meta={
                    "filename": img.filename,
                    "mime_type": img.mime_type,
                },
            )

    def txt2vid_mochi(
        self, config: ComfyuiTxt2VidConfig
    ):
        mochi_repo_id = "Comfy-Org/mochi_preview_repackaged"
        if config.model_name == "":
            # download model
            config.model_name = self.model_manager.download_hugging_face(
                mochi_repo_id,
                "split_files/diffusion_models/mochi_preview_fp8_scaled.safetensors",
                "diffusion_models",
            )
        clip_name = self.model_manager.download_hugging_face(
            mochi_repo_id,
            "split_files/text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors",
            "text_encoders",
        )
        vae_name = self.model_manager.download_hugging_face(
            mochi_repo_id,
            "split_files/vae/mochi_vae.safetensors",
            "vae",
        )

        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_dir, "json", "txt2vid_mochi.json")) as file:
            workflow = ComfyUiWorkflow(file.read())

        workflow.set_Ksampler(
            None,
            config.steps,
            config.sampler_name,
            config.scheduler_name,
            config.cfg,
            1.0,
            random.randint(0, 100000000),
        )
        workflow.set_property("28", "inputs/fps", config.fps)
        workflow.set_empty_mochi(
            None, config.width, config.height, config.frameN)
        workflow.set_unet(None, config.model_name)
        workflow.set_clip(None, clip_name)
        workflow.set_vae(None, vae_name)
        workflow.set_prompt("6", config.prompt)
        workflow.set_prompt("7", config.negative_prompt)

        try:
            output_images = self.comfyui.generate(workflow.json())
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to generate image: {str(e)}"
            )
        return output_images

    def txt2vid_hunyuan(
        self, config: ComfyuiTxt2VidConfig
    ):
        hunyuan_repo_id = "Comfy-Org/HunyuanVideo_repackaged"
        if config.model_name == "":
            # download model
            config.model_name = self.model_manager.download_hugging_face(
                hunyuan_repo_id,
                "split_files/diffusion_models/hunyuan_video_t2v_720p_bf16.safetensors",
                "diffusion_models",
            )
        clip_name1 = self.model_manager.download_hugging_face(
            hunyuan_repo_id,
            "split_files/text_encoders/clip_l.safetensors",
            "text_encoders",
        )
        clip_name2 = self.model_manager.download_hugging_face(
            hunyuan_repo_id,
            "split_files/text_encoders/llava_llama3_fp8_scaled.safetensors",
            "text_encoders",
        )
        vae_name = self.model_manager.download_hugging_face(
            hunyuan_repo_id,
            "split_files/vae/hunyuan_video_vae_bf16.safetensors",
            "vae",
        )
        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_dir, "json", "txt2vid_hunyuan.json")) as file:
            workflow = ComfyUiWorkflow(file.read())
        workflow.set_Ksampler(
            None,
            config.steps,
            config.sampler_name,
            config.scheduler_name,
            config.cfg,
            1.0,
            random.randint(0, 100000000),
        )
        workflow.set_dual_clip(None, clip_name1, clip_name2)
        workflow.set_unet(None, config.model_name)
        workflow.set_vae(None, vae_name)
        workflow.set_empty_hunyuan(
            None, config.width, config.height, config.frameN)
        workflow.set_prompt(None, config.prompt)

        try:
            output_images = self.comfyui.generate(workflow.json())
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to generate image: {str(e)}"
            )
        return output_images

    def txt2vid_wan2_1(
        self, config: ComfyuiTxt2VidConfig
    ):
        wan_repo_id = "Comfy-Org/Wan_2.1_ComfyUI_repackaged"
        if config.model_name == "":
            # download model
            config.model_name = self.model_manager.download_hugging_face(
                wan_repo_id,
                "split_files/diffusion_models/wan2.1_t2v_14B_fp8_e4m3fn.safetensors",
                "diffusion_models",
            )
        vae = self.model_manager.download_hugging_face(
            wan_repo_id,
            "split_files/vae/wan_2.1_vae.safetensors",
            "vae",
        )
        text_encoder = self.model_manager.download_hugging_face(
            wan_repo_id,
            "split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors",
            "text_encoders",
        )
        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_dir, "json", "txt2vid_wan2_1.json")) as file:
            workflow = ComfyUiWorkflow(file.read())

        workflow.set_prompt("6", config.prompt)
        workflow.set_prompt("7", config.negative_prompt)

        webp_node_id = workflow.identify_node_by_class_type("SaveAnimatedWEBP")
        workflow.set_property(webp_node_id, "inputs/fps", config.fps)
        workflow.set_unet(None, config.model_name)
        workflow.set_clip(None, text_encoder)
        workflow.set_vae(None, vae)
        workflow.set_empty_hunyuan(
            None, config.width, config.height, config.frameN)

        try:
            output_images = self.comfyui.generate(workflow.json())
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to generate image: {str(e)}"
            )
        return output_images

    def txt2vid_wan2_2_14B(
        self, config: ComfyuiTxt2VidConfig
    ):
        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(
            os.path.join(current_dir, "json", "txt2vid_wan2_2_14B.json"),
            encoding="UTF-8",
        ) as file:
            workflow = ComfyUiWorkflow(file.read())
            self.model_manager.download_from_json(workflow.json_original_str())

        workflow.set_prompt("89", config.prompt)
        workflow.set_prompt("72", config.negative_prompt)

        workflow.set_empty_hunyuan(
            None, config.width, config.height, config.frameN)

        try:
            output_images = self.comfyui.generate(workflow.json())
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to generate image: {str(e)}"
            )
        return output_images

    def txt2vid_wan2_2_5B(
        self, config: ComfyuiTxt2VidConfig
    ):
        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(
            os.path.join(current_dir, "json", "txt2vid_wan2_2_5B.json"),
            encoding="UTF-8",
        ) as file:
            workflow = ComfyUiWorkflow(file.read())
            self.model_manager.download_from_json(workflow.json_original_str())

        workflow.set_prompt("6", config.prompt)
        workflow.set_prompt("7", config.negative_prompt)

        wan2_2 = workflow.identify_node_by_class_type(
            "Wan22ImageToVideoLatent")
        workflow.set_property(wan2_2, "inputs/width", config.width)
        workflow.set_property(wan2_2, "inputs/height", config.height)
        workflow.set_property(wan2_2, "inputs/length", config.frameN)

        try:
            output_images = self.comfyui.generate(workflow.json())
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to generate image: {str(e)}"
            )
        return output_images

    def txt2vid_ltxv(
        self, config: ComfyuiTxt2VidConfig
    ):
        ltxv_repo_id = "Lightricks/LTX-Video"
        if config.model_name == "":
            # download model
            config.model_name = self.model_manager.download_hugging_face(
                ltxv_repo_id,
                "ltx-video-2b-v0.9.safetensors",
                "checkpoints",
            )
        text_encoder = self.model_manager.download_hugging_face(
            ltxv_repo_id,
            "t5xxl_fp16.safetensors",
            "text_encoders",
        )

        current_dir = os.path.dirname(os.path.realpath(__file__))
        with open(os.path.join(current_dir, "json", "txt2vid_ltxv.json")) as file:
            workflow = ComfyUiWorkflow(file.read())

        webp_node_id = workflow.identify_node_by_class_type("SaveAnimatedWEBP")
        workflow.set_property(webp_node_id, "inputs/fps", config.fps)

        workflow.set_prompt("6", config.prompt)
        workflow.set_prompt("7", config.negative_prompt)
        workflow.set_property("38", "inputs/clip_name", text_encoder)
        workflow.set_property("72", "inputs/noise_seed",
                              random.randint(0, 100000000))
        ltxv_node_id = workflow.identify_node_by_class_type(
            "EmptyLTXVLatentVideo")
        workflow.set_property(ltxv_node_id, "inputs/width", config.width)
        workflow.set_property(ltxv_node_id, "inputs/height", config.height)
        workflow.set_property(ltxv_node_id, "inputs/length", config.frameN)

        try:
            output_images = self.comfyui.generate(workflow.json())
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to generate image: {str(e)}"
            )
        return output_images

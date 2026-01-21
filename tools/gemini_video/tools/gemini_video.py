import json
import logging
import time
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

SUPPORTED_MODELS = [
    "veo-3.1-generate-preview",
    "veo-3.1-fast-generate-preview"
]


class GeminiVideoTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Video generation does not support streaming. So we can just yield the blob result.

        # Parameters
        model = tool_parameters.get('model', "veo-3.1-fast-generate-preview")
        proxy_url = tool_parameters.get('proxy_url', None)
        if model not in SUPPORTED_MODELS:
            raise InvokeError(f"model:{model} is not supported")
        _gemini_api_key = self.runtime.credentials["gemini_api_key"]

        # Init source & Config
        source = types.GenerateVideosSource()
        config = types.GenerateVideosConfig()

        # Valid parameters
        self._valid_parameters(tool_parameters, config, source)

        # invoke video generation
        genai_client = genai.Client(
            api_key=_gemini_api_key,
            http_options=types.HttpOptions(
                base_url=tool_parameters.get('base_url', None),
            )
        )
        operation: types.GenerateVideosOperation = genai_client.models.generate_videos(
            model=model,
            source=source,
            config=config
        )

        # Poll the operation status until the video is ready
        while not operation.done:
            logger.info("Waiting for video generation to complete...")
            time.sleep(10)
            operation = genai_client.operations.get(operation)

        # Download the video
        video = operation.response.generated_videos[0]
        genai_client.files.download(file=video.video)

        # yield blob message
        final_video = video.video
        yield self.create_blob_message(
            blob=final_video.video_bytes,
            # the generated video must be a mp4 file
            # and Dify file system won't care about the filename
            # just let it be 'output.mp4'
            # it is only for display purpose
            # to avoid a downloading error, remember to set proper value for FILES_URL and INTERNAL_FILES_URL
            meta={
                "mime_type": "video/mp4",
                "filename": f'output.mp4',
            }
        )

    def _valid_parameters(self, tool_parameters: dict[str, Any], config: types.GenerateVideosConfig, source: types.GenerateVideosSource):
        model = tool_parameters.get('model')
        prompt = tool_parameters.get('prompt')
        negative_prompt = tool_parameters.get('negative_prompt')
        image = tool_parameters.get('image')
        last_frame = tool_parameters.get('last_frame')
        ref_images = tool_parameters.get('ref_images')
        ref_video = tool_parameters.get('ref_video')
        aspect_ratio = tool_parameters.get('aspect_ratio', "16:9")
        resolution = tool_parameters.get('resolution', "720p")
        duration_seconds = tool_parameters.get('duration_seconds')
        person_generation = tool_parameters.get('person_generation')

        # 1 common check
        if not model:
            raise InvokeError("model is required")
        if not prompt:
            raise InvokeError("prompt is required")

        # 2 specific check
        if "3.1" in model:
            # Veo3.1 specific check
            if last_frame and not image:
                raise InvokeError("first image is required when last_frame is set")

            if ref_images and len(ref_images) > 3:
                raise InvokeError("ref_images count can not be more than 3")
        else:
            # you can add more parameter check here for other models
            pass

        # you may change these settings according to the latest official documentation & SDK
        # this is the settings needed for 3.1 right now (2026-01-12)
        # REF: https://ai.google.dev/gemini-api/docs/video?hl=zh-cn&example=dialogue#veo-model-parameters

        # settings for source
        source.prompt = prompt
        source.image = types.Image(image_bytes=image.blob, mime_type=image.mime_type) if image else None
        source.video = types.Video(video_bytes=ref_video.blob, mime_type=ref_video.mime_type) if ref_video else None

        # settings for config
        config.duration_seconds = int(duration_seconds)
        config.aspect_ratio = aspect_ratio
        config.resolution = resolution
        # config.person_generation = person_generation
        config.negative_prompt = negative_prompt
        config.last_frame = types.Image(image_bytes=last_frame.blob, mime_type=last_frame.mime_type) if last_frame else None
        config.reference_images = [types.Image(image_bytes=image.blob, mime_type=image.mime_type) for image in ref_images] if ref_images else None

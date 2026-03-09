import logging
import time
from collections.abc import Generator
from typing import Any

import httpx
import requests
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
        # when using genai to download a video, there seems an existing bug with proxy.
        # the download will fail with a 302 error.
        # so far the way to fix this issue is to directly request the file via proxy
        if proxy_url:
            genai_client = genai.Client(
                api_key=_gemini_api_key,
                http_options=types.HttpOptions(
                    httpx_client=httpx.Client(proxy=proxy_url)
                )
            )
        else:
            genai_client = genai.Client(api_key=_gemini_api_key)
        operation: types.GenerateVideosOperation = genai_client.models.generate_videos(
            model=model,
            source=source,
            config=config
        )

        # Poll the operation status until the video is ready
        # wait for 10 seconds, maximum wait times is 60 iters (10 minutes)
        wait_times = 0
        while not operation.done and wait_times < 60:
            logger.info("Waiting for video generation to complete...")
            time.sleep(10)
            operation = genai_client.operations.get(operation)
            if operation.error:
                raise InvokeError(f"video generation failed: {operation.error.message}")
            wait_times += 1

        if not operation.done:
            raise InvokeError("video generation timeout after 10 minutes")

        # Download the video
        generated_video: types.GeneratedVideo = operation.response.generated_videos[0] if operation.response.generated_videos else None
        if generated_video is None:
            raise InvokeError("video generation failed: no video data returned")

        if proxy_url:
            logger.info("Using proxy to download video...")
            # if generate succeed, the video must contain an url. it won't be None.
            video_uri = generated_video.video.uri
            # add api key to the video url, or you cannot get that file due to unauthorized error
            # add api key to the request header for security
            headers = {'x-goog-api-key': _gemini_api_key}
            # directly request the video file
            rsp = requests.get(
                video_uri,
                proxies={
                    "http": proxy_url,
                    "https": proxy_url
                },
                headers=headers
            )
            rsp.raise_for_status()
            # construct video instance
            video = types.Video(
                uri=video_uri,
                video_bytes=rsp.content
            )
        else:
            logger.info("Using SDK to download video...")
            # use genai to download the video, file bytes will directly write into generated_video.video
            genai_client.files.download(file=generated_video.video)
            video = generated_video.video

        # yield blob message
        # this will return the file(s) return of the tool
        yield self.create_blob_message(
            blob=video.video_bytes,
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
        model = tool_parameters.get('model', 'veo-3.1-fast-generate-preview')
        prompt = tool_parameters.get('prompt')
        negative_prompt = tool_parameters.get('negative_prompt')
        image = tool_parameters.get('image')
        last_frame = tool_parameters.get('last_frame')
        ref_images = tool_parameters.get('ref_images')
        ref_video = tool_parameters.get('ref_video')
        aspect_ratio = tool_parameters.get('aspect_ratio', "16:9")
        resolution = tool_parameters.get('resolution', "720p")
        duration_seconds = tool_parameters.get('duration_seconds', '4')

        # 1 common check
        if not prompt:
            raise InvokeError("prompt is required")
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
        # person_generation is not supported for now
        config.duration_seconds = int(duration_seconds)
        config.aspect_ratio = aspect_ratio
        config.resolution = resolution
        config.negative_prompt = negative_prompt
        config.last_frame = types.Image(image_bytes=last_frame.blob, mime_type=last_frame.mime_type) if last_frame else None
        config.reference_images = [types.Image(image_bytes=image.blob, mime_type=image.mime_type) for image in ref_images] if ref_images else None

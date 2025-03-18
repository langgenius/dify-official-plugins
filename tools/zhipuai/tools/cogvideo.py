import time
from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from zhipuai import ZhipuAI
from zhipuai.types.video import VideoObject


class CogVideoTool(Tool):
    def _invoke(
            self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        client = ZhipuAI(
            base_url=self.runtime.credentials["zhipuai_base_url"],
            api_key=self.runtime.credentials["zhipuai_api_key"],
        )
        gen = self._start_video_generation(client, tool_parameters)
        if isinstance(gen, ToolInvokeMessage):
            yield gen
            return

        completion = self._wait_for_completion(client, gen.id, tool_parameters)

        if isinstance(completion, ToolInvokeMessage):
            yield completion
            return
        yield self.create_json_message(completion.model_dump())

    def _start_video_generation(self, client: ZhipuAI,
                                tool_parameters: dict[str, Any]) -> ToolInvokeMessage | VideoObject:
        model = tool_parameters.get("model", "")
        if not model:
            return self.create_text_message("Please input model")

        if not tool_parameters.get("prompt") and (not tool_parameters.get("image_url")):
            return self.create_text_message("require at least one of prompt and image_url")

        user_id = self.runtime.user_id

        size = tool_parameters.get("size", None)
        fps = tool_parameters.get("fps", None)
        with_audio = tool_parameters.get("with_audio", None)
        quality = tool_parameters.get("quality", None)

        response = client.videos.generations(
            model=model,
            prompt=tool_parameters.get("prompt"),
            image_url=tool_parameters.get("image_url"),
            quality=quality,
            with_audio=with_audio,
            size=size,
            fps=fps,
            user_id=user_id,
        )
        return response

    def _wait_for_completion(self, client: ZhipuAI, video_id: str,
                             tool_parameters: dict[str, Any]) -> ToolInvokeMessage | VideoObject:
        """Wait for video generation completion and handle the result."""
        retry_count = tool_parameters.get("retry_count", 10)
        wait_time = tool_parameters.get("wait_time", 5)
        for i in range(retry_count):
            response = client.videos.retrieve_videos_result(id=video_id)
            status = response.task_status
            if status == "SUCCESS":
                return response
            if status == "PROCESSING":
                time.sleep(wait_time)
                continue
            if status == "FAIL":
                return self.create_text_message(f"Video generation failed.")
            return self.create_text_message(f"Unexpected status: {status}")
        return self.create_text_message("max retry")

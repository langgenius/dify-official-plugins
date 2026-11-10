from typing import Any, Generator
import httpx
from zai import ZhipuAiClient
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class CogVideoJobTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        client = ZhipuAiClient(
            api_key=self.runtime.credentials["zhipuai_api_key"],
            base_url=self.runtime.credentials["zhipuai_base_url"],
        )
        response = client.videos.retrieve_videos_result(id=tool_parameters.get("id"))
        yield self.create_json_message(response.dict())
        if response.task_status == "SUCCESS":
            for item in response.video_result:
                video_cover_image = self.create_image_message(item.cover_image_url)
                yield video_cover_image
                video = self.create_blob_message(
                    blob=httpx.get(item.url).content,
                    meta={"mime_type": "video/mp4"},
                )
                yield video

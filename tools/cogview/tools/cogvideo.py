from typing import Any, Generator
from zai import ZhipuAiClient
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class CogVideoTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        client = ZhipuAiClient(
            base_url=self.runtime.credentials["zhipuai_base_url"],
            api_key=self.runtime.credentials["zhipuai_api_key"],
        )
        if not tool_parameters.get("prompt") and (not tool_parameters.get("image_url")):
            return self.create_text_message(
                "require at least one of prompt and image_url"
            )
        response = client.videos.generations(
            model="cogvideox",
            prompt=tool_parameters.get("prompt"),
            image_url=tool_parameters.get("image_url"),
        )
        yield self.create_json_message(response.dict())

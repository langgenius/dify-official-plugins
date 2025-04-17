from typing import Any, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from zhipuai import ZhipuAI


class CogViewTool(Tool):
    """CogView Series Tool"""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invoke CogView Series tool
        """
        client = ZhipuAI(
            base_url=self.runtime.credentials["zhipuai_base_url"],
            api_key=self.runtime.credentials["zhipuai_api_key"],
        )

        model = tool_parameters.get("model", "")
        if not model:
            yield self.create_text_message("Please input model")

        prompt = tool_parameters.get("prompt", "")
        if not prompt:
            yield self.create_text_message("Please input prompt")

        size = tool_parameters.get("size", "")
        user_id = self.runtime.user_id

        response = client.images.generations(
            prompt=prompt,
            model=model,
            size=size,
            user_id=user_id,
        )
        for image in response.data:
            # yield self.create_image_message(image_url=image.url)
            yield self.create_json_message({"url": image.url})

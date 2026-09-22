import random
from typing import Any, Generator
from zai import ZhipuAiClient
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class CogView3Tool(Tool):
    """CogView3 Tool"""

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invoke CogView3 tool
        """
        client = ZhipuAiClient(
            base_url=self.runtime.credentials["zhipuai_base_url"],
            api_key=self.runtime.credentials["zhipuai_api_key"],
        )
        size_mapping = {
            "square": "1024x1024",
            "vertical_768": "768x1344",
            "vertical_864": "864x1152",
            "horizontal_1344": "1344x768",
            "horizontal_1152": "1152x864",
            "widescreen_1440": "1440x720",
            "tallscreen_720": "720x1440",
        }
        prompt = tool_parameters.get("prompt", "")
        if not prompt:
            yield self.create_text_message("Please input prompt")
        size_key = tool_parameters.get("size", "square")
        if size_key != "cogview_3":
            size = size_mapping[size_key]
        n = tool_parameters.get("n", 1)
        quality = tool_parameters.get("quality", "standard")
        if quality not in {"standard", "hd"}:
            yield self.create_text_message("Invalid quality")
        style = tool_parameters.get("style", "vivid")
        if style not in {"natural", "vivid"}:
            yield self.create_text_message("Invalid style")
        seed_id = tool_parameters.get("seed_id", self._generate_random_id(8))
        extra_body = {"seed": seed_id}
        if size_key != "cogview_3":
            response = client.images.generations(
                prompt=prompt,
                model="cogview-3-plus",
                size=size,
                n=n,
                extra_body=extra_body,
                style=style,
                quality=quality,
                response_format="b64_json",
            )
        else:
            response = client.images.generations(
                prompt=prompt,
                model="cogview-3",
                n=n,
                extra_body=extra_body,
                style=style,
                quality=quality,
                response_format="b64_json",
            )
        for image in response.data:
            yield self.create_image_message(image.url)
            yield self.create_json_message({"url": image.url})

    @staticmethod
    def _generate_random_id(length=8):
        characters = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
        random_id = "".join(random.choices(characters, k=length))
        return random_id

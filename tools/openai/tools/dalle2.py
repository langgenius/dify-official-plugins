from base64 import b64decode
from collections.abc import Generator
from typing import Literal
from openai import OpenAI
from yarl import URL
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class DallE2Tool(Tool):
    def _invoke(
        self, tool_parameters: dict
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        openai_organization = self.runtime.credentials.get(
            "openai_organization_id", None
        )
        if not openai_organization:
            openai_organization = None
        openai_base_url = self.runtime.credentials.get("openai_base_url", None)
        if not openai_base_url:
            openai_base_url = None
        else:
            openai_base_url = str(URL(openai_base_url) / "v1")
        client = OpenAI(
            api_key=self.runtime.credentials["openai_api_key"],
            base_url=openai_base_url,
            organization=openai_organization,
        )
        SIZE_MAPPING = {"small": "256x256", "medium": "512x512", "large": "1024x1024"}
        prompt = tool_parameters.get("prompt", "")
        if not prompt:
            yield self.create_text_message("Please input prompt")

        size: Literal["256x256", "512x512", "1024x1024"] = SIZE_MAPPING[
            tool_parameters.get("size", "large")
        ] # type: ignore

        n = tool_parameters.get("n", 1)
        response = client.images.generate(
            prompt=prompt, model="dall-e-2", size=size, n=n, response_format="b64_json"
        )
        for image in response.data:
            if not image.b64_json:
                continue

            yield self.create_blob_message(
                blob=b64decode(image.b64_json), meta={"mime_type": "image/png"}
            )

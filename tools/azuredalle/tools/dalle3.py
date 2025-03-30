import random
import base64
from typing import Any
from openai import AzureOpenAI
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from collections.abc import Generator

class DallE3Tool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        client = AzureOpenAI(
            api_version=self.runtime.credentials["azure_openai_api_version"],
            azure_endpoint=self.runtime.credentials["azure_openai_base_url"],
            api_key=self.runtime.credentials["azure_openai_api_key"],
        )
        SIZE_MAPPING = {"square": "1024x1024", "vertical": "1024x1792", "horizontal": "1792x1024"}
        prompt = tool_parameters.get("prompt", "")
        if not prompt:
            yield self.create_text_message("Please input prompt")
        size = SIZE_MAPPING[tool_parameters.get("size", "square")]
        n = tool_parameters.get("n", 1)
        quality = tool_parameters.get("quality", "standard")
        if quality not in {"standard", "hd"}:
            yield self.create_text_message("Invalid quality")
        style = tool_parameters.get("style", "vivid")
        if style not in {"natural", "vivid"}:
            yield self.create_text_message("Invalid style")
        seed_id = tool_parameters.get("seed_id", self._generate_random_id(8))
        extra_body = {"seed": seed_id}
        model = self.runtime.credentials["azure_openai_api_model_name"]
        response = client.images.generate(
            prompt=prompt,
            model=model,
            size=size, # type: ignore
            n=n,
            extra_body=extra_body,
            style=style,
            quality=quality,
            response_format="b64_json",
        )
        for image in response.data:
            if not image.b64_json:
                continue
            (mime_type, blob_image) = DallE3Tool._decode_image(image.b64_json)
            yield self.create_blob_message(
                blob=blob_image, meta={"mime_type": mime_type}
            )

    @staticmethod
    def _decode_image(base64_image: str) -> tuple[str, bytes]:
        """
        Decode a base64 encoded image. If the image is not prefixed with a MIME type,
        it assumes 'image/png' as the default.

        :param base64_image: Base64 encoded image string
        :return: A tuple containing the MIME type and the decoded image bytes
        """
        if DallE3Tool._is_plain_base64(base64_image):
            return ("image/png", base64.b64decode(base64_image))
        else:
            return DallE3Tool._extract_mime_and_data(base64_image)

    @staticmethod
    def _is_plain_base64(encoded_str: str) -> bool:
        """
        Check if the given encoded string is plain base64 without a MIME type prefix.

        :param encoded_str: Base64 encoded image string
        :return: True if the string is plain base64, False otherwise
        """
        return not encoded_str.startswith("data:image")

    @staticmethod
    def _extract_mime_and_data(encoded_str: str) -> tuple[str, bytes]:
        """
        Extract MIME type and image data from a base64 encoded string with a MIME type prefix.

        :param encoded_str: Base64 encoded image string with MIME type prefix
        :return: A tuple containing the MIME type and the decoded image bytes
        """
        mime_type = encoded_str.split(";")[0].split(":")[1]
        image_data_base64 = encoded_str.split(",")[1]
        decoded_data = base64.b64decode(image_data_base64)
        return (mime_type, decoded_data)

    @staticmethod
    def _generate_random_id(length=8):
        characters = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
        random_id = "".join(random.choices(characters, k=length))
        return random_id

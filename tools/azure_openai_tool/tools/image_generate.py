import base64
import random
from collections.abc import Generator
from typing import Any, Dict

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from openai import AzureOpenAI


class ImageGenerateTool(Tool):
    def _invoke(
        self, tool_parameters: dict
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        client = AzureOpenAI(
            api_key=self.runtime.credentials["azure_openai_api_key"],
            azure_endpoint=self.runtime.credentials["azure_openai_base_url"],
            api_version=self.runtime.credentials["azure_openai_api_version"],
            azure_deployment=self.runtime.credentials["azure_openai_api_model_name"]
        )

        prompt = tool_parameters.get("prompt", "")
        if not prompt:
            yield self.create_text_message("Please input prompt")
            return
        # --- Parameter Extraction and Validation --- 
        generation_args: Dict[str, Any] = {
            "model": "gpt-image-1",
            "prompt": prompt,
        }

        # Size (optional, defaults to auto)
        size = tool_parameters.get("size", "1024x1024")
        if size not in {"1024x1024", "1536x1024", "1024x1536"}:
            yield self.create_text_message("Invalid size. Choose 1024x1024, 1536x1024 or 1024x1536.")
            return
        generation_args["size"] = size

        # Quality (optional, defaults to auto)
        quality = tool_parameters.get("quality", "high")
        if quality not in {"low", "medium", "high"}:
            yield self.create_text_message("Invalid quality. Choose low, medium, high, or auto.")
            return
        generation_args["quality"] = quality

        # Output Format (optional, defaults to png implicitly via API? Let's allow setting explicitly)
        output_format = tool_parameters.get("output_format", "png")  # Treat 'auto' as unset/use API default
        if output_format not in {"png", "jpeg"}:
            yield self.create_text_message("Invalid output_format. Choose png or jpeg.")
            return

        # Output Compression (optional, defaults to 100)
        output_compression = tool_parameters.get("output_compression", 100)
        generation_args["output_compression"] = output_compression

        # N (optional, defaults to 1)
        n_str = tool_parameters.get("n")
        n = 1  # Default to 1
        if n_str is not None:
            try:
                n = int(n_str)
                if not 1 <= n <= 10:
                    raise ValueError("Number of images (n) must be between 1 and 10.")
            except ValueError as e:
                yield self.create_text_message(f"Invalid n: {e}")
                return
        generation_args["n"] = n  # Include n in generation arguments

        # --- API Call --- 
        try:
            response = client.images.generate(**generation_args)
        except Exception as e:
            yield self.create_text_message(f"Failed to generate image: {str(e)}")
            return

        # --- Process Response --- 
        # Prepare metadata with token usage if available
        metadata = {"mime_type": None}  # Will be set per image
        if hasattr(response, 'usage'):
            usage = response.usage
            metadata.update({
                "token_usage": {
                    "total_tokens": usage.total_tokens,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens
                }
            })
            if hasattr(usage, 'input_tokens_details'):
                details = usage.input_tokens_details
                metadata["token_usage"]["input_tokens_details"] = {
                    "text_tokens": details.text_tokens,
                    "image_tokens": details.image_tokens
                }

        for image in response.data:
            if not image.b64_json:
                continue
            (mime_type, blob_image) = ImageGenerateTool._decode_image(image.b64_json)
            # Determine actual mime_type based on requested format if possible
            final_mime_type = mime_type
            if output_format in {'png', 'jpeg', 'webp'}:
                final_mime_type = f"image/{output_format}"

            metadata["mime_type"] = final_mime_type
            yield self.create_blob_message(blob=blob_image, meta=metadata)

    @staticmethod
    def _decode_image(base64_image: str) -> tuple[str, bytes]:
        """
        Decode a base64 encoded image. If the image is not prefixed with a MIME type,
        it assumes 'image/png' as the default.

        :param base64_image: Base64 encoded image string
        :return: A tuple containing the MIME type and the decoded image bytes
        """
        if ImageGenerateTool._is_plain_base64(base64_image):
            # Default assumption, might be overridden later based on output_format
            return "image/png", base64.b64decode(base64_image)
        else:
            return ImageGenerateTool._extract_mime_and_data(base64_image)

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
        try:
            mime_type = encoded_str.split(";")[0].split(":")[1]
            image_data_base64 = encoded_str.split(",")[1]
            decoded_data = base64.b64decode(image_data_base64)
            return mime_type, decoded_data
        except (IndexError, ValueError):
            # Handle potential malformed base64 string gracefully
            # Fallback or raise specific error?
            # Fallback to default png for now
            return "image/png", base64.b64decode(encoded_str)  # Attempt to decode anyway if prefix malformed

    @staticmethod
    def _generate_random_id(length=8):
        characters = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
        random_id = "".join(random.choices(characters, k=length))
        return random_id

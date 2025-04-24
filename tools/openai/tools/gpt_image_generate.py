import base64
import random
from collections.abc import Generator
from typing import Any, Dict, Optional
from openai import OpenAI
from yarl import URL
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class GPTImageGenerateTool(Tool):
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
        size = tool_parameters.get("size", "auto")
        if size not in {"1024x1024", "1536x1024", "1024x1536", "auto"}:
             yield self.create_text_message("Invalid size. Choose 1024x1024, 1536x1024, 1024x1536, or auto.")
             return
        if size != "auto": # Only include if not default
            generation_args["size"] = size

        # Quality (optional, defaults to auto)
        quality = tool_parameters.get("quality", "auto")
        if quality not in {"low", "medium", "high", "auto"}:
            yield self.create_text_message("Invalid quality. Choose low, medium, high, or auto.")
            return
        if quality != "auto": # Only include if not default
            generation_args["quality"] = quality

        # Background (optional, defaults to auto)
        background = tool_parameters.get("background", "auto")
        if background not in {"opaque", "transparent", "auto"}:
            yield self.create_text_message("Invalid background. Choose opaque, transparent, or auto.")
            return
        if background != "auto": # Only include if not default
            generation_args["background"] = background
            # Auto-fix output format for transparent background
            if background == "transparent":
                output_format = tool_parameters.get("output_format", "png")  # Default to png for transparency
                if output_format not in {"png", "webp"}:
                    output_format = "png"  # Force png if incompatible format was selected
                generation_args["output_format"] = output_format

        # Output Format (optional, defaults to png implicitly via API? Let's allow setting explicitly)
        output_format = tool_parameters.get("output_format", "auto") # Treat 'auto' as unset/use API default
        if output_format not in {"png", "jpeg", "webp", "auto"}:
            yield self.create_text_message("Invalid output_format. Choose png, jpeg, webp, or auto.")
            return
        if output_format != "auto" and background != "transparent":  # Only set if not auto and not already set by transparency logic
             generation_args["output_format"] = output_format
             # Ensure background compatibility with output format if background is transparent
             if background == "transparent" and output_format == "jpeg":
                 yield self.create_text_message("Transparent background requires png or webp output format.")
                 return

        # Output Compression (optional, defaults to 100, only for jpeg/webp)
        output_compression_str = tool_parameters.get("output_compression")
        if output_compression_str is not None:
            try:
                output_compression = int(output_compression_str)
                if not 0 <= output_compression <= 100:
                    raise ValueError("Compression must be between 0 and 100")
                # Only apply compression for jpeg/webp formats and if not default value
                if output_format in {"jpeg", "webp"} and output_compression != 100:
                    generation_args["output_compression"] = output_compression
            except ValueError as e:
                yield self.create_text_message(f"Invalid output_compression: {e}")
                return

        # Moderation (optional, defaults to auto)
        moderation = tool_parameters.get("moderation", "auto")
        if moderation not in {"low", "auto"}:
            yield self.create_text_message("Invalid moderation. Choose low or auto.")
            return
        if moderation != "auto": # Only include if not default
            generation_args["moderation"] = moderation

        # N (optional, defaults to 1)
        n_str = tool_parameters.get("n")
        n = 1 # Default to 1
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
            (mime_type, blob_image) = GPTImageGenerateTool._decode_image(image.b64_json)
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
        if GPTImageGenerateTool._is_plain_base64(base64_image):
            # Default assumption, might be overridden later based on output_format
            return ("image/png", base64.b64decode(base64_image))
        else:
            return GPTImageGenerateTool._extract_mime_and_data(base64_image)

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
             return (mime_type, decoded_data)
        except (IndexError, ValueError) as e:
            # Handle potential malformed base64 string gracefully
            # Fallback or raise specific error?
            # Fallback to default png for now
            return ("image/png", base64.b64decode(encoded_str)) # Attempt decode anyway if prefix malformed

    @staticmethod
    def _generate_random_id(length=8):
        characters = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
        random_id = "".join(random.choices(characters, k=length))
        return random_id

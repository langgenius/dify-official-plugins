import logging
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from openai import OpenAI
from yarl import URL

from tools._image_utils import build_usage_metadata, build_usage_output, decode_image

logger = logging.getLogger(__name__)


class GPTImage2GenerateTool(Tool):
    def _invoke(
        self, tool_parameters: dict
    ) -> Generator[ToolInvokeMessage, None, None]:
        logger.info(
            "gpt-image-2 generate invoked: prompt_len=%s size=%s quality=%s format=%s moderation=%s n=%s",
            len(tool_parameters.get("prompt", "") or ""),
            tool_parameters.get("size", "auto"),
            tool_parameters.get("quality", "auto"),
            tool_parameters.get("output_format", "auto"),
            tool_parameters.get("moderation", "auto"),
            tool_parameters.get("n", 1),
        )
        openai_organization = self.runtime.credentials.get("openai_organization_id") or None
        openai_base_url = self.runtime.credentials.get("openai_base_url") or None
        if openai_base_url:
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

        background = tool_parameters.get("background", "auto")
        if background not in {"auto", "opaque", "transparent"}:
            yield self.create_text_message("Invalid background. Choose opaque or auto.")
            return
        if background == "transparent":
            yield self.create_text_message(
                "Invalid background. gpt-image-2 does not support transparent background."
            )
            return

        generation_args: dict[str, Any] = {
            "model": "gpt-image-2",
            "prompt": prompt,
        }

        size = tool_parameters.get("size", "auto")
        if size and size != "auto":
            generation_args["size"] = str(size)

        quality = tool_parameters.get("quality", "auto")
        if quality not in {"low", "medium", "high", "auto"}:
            yield self.create_text_message("Invalid quality. Choose low, medium, high, or auto.")
            return
        if quality != "auto":
            generation_args["quality"] = quality

        output_format = tool_parameters.get("output_format", "auto")
        if output_format not in {"png", "jpeg", "webp", "auto"}:
            yield self.create_text_message("Invalid output_format. Choose png, jpeg, webp, or auto.")
            return
        if output_format != "auto":
            generation_args["output_format"] = output_format

        output_compression = tool_parameters.get("output_compression")
        if output_compression not in (None, ""):
            try:
                output_compression = int(output_compression)
            except (TypeError, ValueError):
                yield self.create_text_message(
                    "Invalid output_compression. Choose an integer between 0 and 100."
                )
                return

            if not 0 <= output_compression <= 100:
                yield self.create_text_message(
                    "Invalid output_compression. Choose an integer between 0 and 100."
                )
                return
            if output_format in {"jpeg", "webp"}:
                generation_args["output_compression"] = output_compression

        moderation = tool_parameters.get("moderation", "auto")
        if moderation not in {"low", "auto"}:
            yield self.create_text_message("Invalid moderation. Choose low or auto.")
            return
        if moderation != "auto":
            generation_args["moderation"] = moderation

        n = tool_parameters.get("n", 1)
        try:
            n = int(n)
        except (TypeError, ValueError):
            yield self.create_text_message("Invalid n value. Must be a number between 1 and 10.")
            return
        if not 1 <= n <= 10:
            yield self.create_text_message("Invalid n value. Must be between 1 and 10.")
            return
        generation_args["n"] = n

        try:
            logger.info("gpt-image-2 generate request args: %s", generation_args)
            response = client.images.generate(**generation_args)
        except Exception as e:
            logger.exception("gpt-image-2 generate failed")
            yield self.create_text_message(f"Failed to generate image: {str(e)}")
            return

        usage_metadata = build_usage_metadata(response)
        image_count = len(getattr(response, "data", []))
        logger.info("gpt-image-2 generate success: images=%s", image_count)

        for image in response.data:
            if not image.b64_json:
                continue
            mime_type, blob_image = decode_image(image.b64_json)
            final_mime_type = mime_type
            if output_format in {"png", "jpeg", "webp"}:
                final_mime_type = f"image/{output_format}"

            metadata = {"mime_type": final_mime_type, **usage_metadata}
            yield self.create_blob_message(blob=blob_image, meta=metadata)

        usage_output = build_usage_output(
            response=response,
            model="gpt-image-2",
            operation="generate",
            image_count=image_count,
        )
        if usage_output:
            yield self.create_json_message(usage_output)

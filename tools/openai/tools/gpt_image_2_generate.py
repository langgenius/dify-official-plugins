import logging
from collections.abc import Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from openai import OpenAI
from openai_client import normalize_openai_base_url
from tools._image_utils import (
    build_image_args,
    build_usage_metadata,
    build_usage_output,
    decode_image,
)

logger = logging.getLogger(__name__)


class GPTImage2GenerateTool(Tool):
    def _invoke(self, tool_parameters: dict) -> Generator[ToolInvokeMessage, None, None]:
        try:
            generation_args = build_image_args(tool_parameters)
            moderation = tool_parameters.get("moderation", "auto")
            if moderation not in ("auto", "low"):
                raise ValueError("Invalid moderation. Choose low or auto.")
            if moderation != "auto":
                generation_args["moderation"] = moderation
        except ValueError as e:
            yield self.create_text_message(str(e))
            return

        model = generation_args["model"]
        output_format = generation_args.get("output_format", "auto")
        try:
            client = OpenAI(
                api_key=self.runtime.credentials["openai_api_key"],
                base_url=normalize_openai_base_url(self.runtime.credentials.get("openai_base_url")),
                organization=self.runtime.credentials.get("openai_organization_id") or None,
            )
            logger.info(
                "%s generate: size=%s quality=%s n=%s",
                model,
                generation_args.get("size", "auto"),
                generation_args.get("quality", "auto"),
                generation_args["n"],
            )
            response = client.images.generate(**generation_args)
        except Exception as e:
            logger.exception("%s generate failed", model)
            yield self.create_text_message(f"Failed to generate image: {e!s}")
            return

        usage_metadata = build_usage_metadata(response)
        image_count = len(getattr(response, "data", []))
        logger.info("%s generate success: images=%s", model, image_count)

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
            model=model,
            operation="generate",
            image_count=image_count,
        )
        if usage_output:
            yield self.create_json_message(usage_output)

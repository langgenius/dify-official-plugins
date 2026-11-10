import io
import logging
from collections.abc import Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.file.file import File
from openai import OpenAI
from openai_client import normalize_openai_base_url
from tools._image_utils import (
    build_image_args,
    build_usage_metadata,
    build_usage_output,
    decode_image,
)

logger = logging.getLogger(__name__)


class GPTImage2EditTool(Tool):
    def _invoke(self, tool_parameters: dict) -> Generator[ToolInvokeMessage, None, None]:
        try:
            edit_args = build_image_args(tool_parameters)
        except ValueError as e:
            yield self.create_text_message(str(e))
            return

        image = tool_parameters.get("image")
        if not image:
            yield self.create_text_message("Error: Input image file is required.")
            return
        if isinstance(image, list) and len(image) > 16:
            yield self.create_text_message("Error: At most 16 input images are supported.")
            return

        model = edit_args["model"]
        output_format = edit_args.get("output_format", "auto")
        image_files: list[io.BytesIO] = []
        mask_file: io.BytesIO | None = None

        try:
            if isinstance(image, list):
                for img in image:
                    if not isinstance(img, File):
                        yield self.create_text_message(
                            "Error: All input images must be valid files."
                        )
                        return
                    img_file = io.BytesIO(img.blob)
                    img_file.name = getattr(img, "filename", "input_image.png")
                    image_files.append(img_file)
                edit_args["image"] = image_files
            else:
                if not isinstance(image, File):
                    yield self.create_text_message("Error: Input image must be a valid file.")
                    return
                img_file = io.BytesIO(image.blob)
                img_file.name = getattr(image, "filename", "input_image.png")
                image_files.append(img_file)
                edit_args["image"] = img_file

            mask = tool_parameters.get("mask")
            if mask:
                if not isinstance(mask, File):
                    yield self.create_text_message("Error: Mask image must be a valid file.")
                    return
                mask_file = io.BytesIO(mask.blob)
                mask_file.name = getattr(mask, "filename", "mask_image.png")
                edit_args["mask"] = mask_file

            client = OpenAI(
                api_key=self.runtime.credentials["openai_api_key"],
                base_url=normalize_openai_base_url(self.runtime.credentials.get("openai_base_url")),
                organization=self.runtime.credentials.get("openai_organization_id") or None,
            )
            logger.info(
                "image edit: model=%s size=%s quality=%s n=%s has_mask=%s",
                edit_args["model"],
                edit_args.get("size", "auto"),
                edit_args.get("quality", "auto"),
                edit_args["n"],
                "mask" in edit_args,
            )
            response = client.images.edit(**edit_args)
        except Exception as e:
            logger.exception("%s edit failed", model)
            yield self.create_text_message(f"Failed to edit image: {e!s}")
            return
        finally:
            for file_obj in image_files:
                if not file_obj.closed:
                    file_obj.close()
            if mask_file and not mask_file.closed:
                mask_file.close()

        usage_metadata = build_usage_metadata(response)
        image_count = len(getattr(response, "data", []))
        logger.info("%s edit success: images=%s", model, image_count)
        for image_data in response.data:
            if not image_data.b64_json:
                continue
            mime_type, blob_image = decode_image(image_data.b64_json)
            if output_format in {"png", "jpeg", "webp"}:
                mime_type = f"image/{output_format}"
            metadata = {"mime_type": mime_type, **usage_metadata}
            yield self.create_blob_message(blob=blob_image, meta=metadata)

        usage_output = build_usage_output(
            response=response,
            model=model,
            operation="edit",
            image_count=image_count,
        )
        if usage_output:
            yield self.create_json_message(usage_output)

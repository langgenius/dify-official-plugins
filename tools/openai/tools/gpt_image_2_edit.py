import io
import logging
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.file.file import File
from openai import OpenAI
from yarl import URL

from tools._image_utils import build_usage_metadata, build_usage_output, decode_image

logger = logging.getLogger(__name__)


class GPTImage2EditTool(Tool):
    def _invoke(
        self, tool_parameters: dict
    ) -> Generator[ToolInvokeMessage, None, None]:
        image = tool_parameters.get("image")
        image_count = len(image) if isinstance(image, list) else (1 if image else 0)
        logger.info(
            "gpt-image-2 edit invoked: prompt_len=%s images=%s has_mask=%s size=%s quality=%s n=%s",
            len(tool_parameters.get("prompt", "") or ""),
            image_count,
            bool(tool_parameters.get("mask")),
            tool_parameters.get("size", "auto"),
            tool_parameters.get("quality", "auto"),
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

        prompt = tool_parameters.get("prompt")
        if not prompt or not isinstance(prompt, str):
            yield self.create_text_message("Error: Prompt is required.")
            return

        if not image:
            yield self.create_text_message("Error: Input image file is required.")
            return

        edit_args: dict[str, Any] = {
            "model": "gpt-image-2",
            "prompt": prompt,
        }
        image_files: list[io.BytesIO] = []
        mask_file: io.BytesIO | None = None

        try:
            if isinstance(image, list):
                if not image:
                    yield self.create_text_message("Error: Input image file is required.")
                    return
                for img in image:
                    if not isinstance(img, File):
                        yield self.create_text_message("Error: All input images must be valid files.")
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

            size = tool_parameters.get("size", "auto")
            if size and size != "auto":
                edit_args["size"] = str(size)

            quality = tool_parameters.get("quality", "auto")
            if quality not in {"low", "medium", "high", "auto"}:
                yield self.create_text_message("Invalid quality. Choose low, medium, high, or auto.")
                return
            if quality != "auto":
                edit_args["quality"] = quality

            n = tool_parameters.get("n", 1)
            try:
                n = int(n)
            except (TypeError, ValueError):
                yield self.create_text_message("Invalid n value. Must be a number between 1 and 10.")
                return
            if not 1 <= n <= 10:
                yield self.create_text_message("Invalid n value. Must be between 1 and 10.")
                return
            edit_args["n"] = n

            logger.info(
                "gpt-image-2 edit request args: model=%s size=%s quality=%s n=%s has_mask=%s",
                edit_args["model"],
                edit_args.get("size", "auto"),
                edit_args.get("quality", "auto"),
                edit_args["n"],
                "mask" in edit_args,
            )
            response = client.images.edit(**edit_args)
        except Exception as e:
            logger.exception("gpt-image-2 edit failed")
            yield self.create_text_message(f"Failed to edit image: {str(e)}")
            return
        finally:
            for file_obj in image_files:
                if not file_obj.closed:
                    file_obj.close()
            if mask_file and not mask_file.closed:
                mask_file.close()

        usage_metadata = build_usage_metadata(response)
        image_count = len(getattr(response, "data", []))
        logger.info("gpt-image-2 edit success: images=%s", image_count)
        for image_data in response.data:
            if not image_data.b64_json:
                continue
            mime_type, blob_image = decode_image(image_data.b64_json)
            metadata = {"mime_type": mime_type, **usage_metadata}
            yield self.create_blob_message(blob=blob_image, meta=metadata)

        usage_output = build_usage_output(
            response=response,
            model="gpt-image-2",
            operation="edit",
            image_count=image_count,
        )
        if usage_output:
            yield self.create_json_message(usage_output)

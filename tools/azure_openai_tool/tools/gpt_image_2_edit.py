import io
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.file.file import File
from openai import AzureOpenAI

from tools._image_utils import (
    build_usage_output_from_metadata,
    decode_image,
    is_size_string,
    merge_usage_metadata,
)


class GPTImage2EditTool(Tool):
    def _invoke(
        self, tool_parameters: dict
    ) -> Generator[ToolInvokeMessage, None, None]:
        deployment_name = self.runtime.credentials["azure_openai_api_model_name"]
        client = AzureOpenAI(
            api_key=self.runtime.credentials["azure_openai_api_key"],
            azure_endpoint=self.runtime.credentials["azure_openai_base_url"],
            api_version=self.runtime.credentials["azure_openai_api_version"],
        )

        prompt = tool_parameters.get("prompt")
        if not prompt or not isinstance(prompt, str):
            yield self.create_text_message("Error: Prompt is required.")
            return

        image = tool_parameters.get("image")
        if not image:
            yield self.create_text_message("Error: Input image file is required.")
            return

        edit_args: dict[str, Any] = {
            "model": deployment_name,
            "prompt": prompt,
        }
        image_payloads: list[tuple[bytes, str]] = []
        mask_payload: tuple[bytes, str] | None = None

        def _make_named_file(blob: bytes, filename: str) -> io.BytesIO:
            file_obj = io.BytesIO(blob)
            file_obj.name = filename
            return file_obj

        def _invoke_edit(request_n: int) -> Any:
            request_args = dict(edit_args)
            request_args["n"] = request_n

            image_files = [_make_named_file(blob, filename) for blob, filename in image_payloads]
            mask_file = _make_named_file(*mask_payload) if mask_payload else None

            try:
                if len(image_files) == 1:
                    request_args["image"] = image_files[0]
                else:
                    request_args["image"] = image_files

                if mask_file:
                    request_args["mask"] = mask_file

                return client.images.edit(**request_args)
            finally:
                for file_obj in image_files:
                    if not file_obj.closed:
                        file_obj.close()
                if mask_file and not mask_file.closed:
                    mask_file.close()

        try:
            if isinstance(image, list):
                if not image:
                    yield self.create_text_message("Error: Input image file is required.")
                    return
                for img in image:
                    if not isinstance(img, File):
                        yield self.create_text_message("Error: All input images must be valid files.")
                        return
                    image_payloads.append((img.blob, getattr(img, "filename", "input_image.png")))
            else:
                if not isinstance(image, File):
                    yield self.create_text_message("Error: Input image must be a valid file.")
                    return
                image_payloads.append((image.blob, getattr(image, "filename", "input_image.png")))

            mask = tool_parameters.get("mask")
            if mask:
                if not isinstance(mask, File):
                    yield self.create_text_message("Error: Mask image must be a valid file.")
                    return
                mask_payload = (mask.blob, getattr(mask, "filename", "mask_image.png"))

            size = tool_parameters.get("size", "1024x1024")
            if not isinstance(size, str) or not is_size_string(size):
                yield self.create_text_message("Invalid size. Use a WxH string such as 1024x1024 or 1536x1024.")
                return
            edit_args["size"] = size

            quality = tool_parameters.get("quality", "high")
            if quality not in {"low", "medium", "high"}:
                yield self.create_text_message("Invalid quality. Choose low, medium, or high.")
                return
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
            response = _invoke_edit(n)
        except Exception:
            yield self.create_text_message(
                "Failed to edit image. Check the Azure OpenAI deployment, API version, and edit inputs."
            )
            return

        try:
            responses = [response]
            images = list(getattr(response, "data", []))
            fallback_used = False
            attempts = 1

            while len(images) < n and attempts < n:
                remaining = n - len(images)
                fallback_used = True
                extra_response = _invoke_edit(remaining)
                extra_images = list(getattr(extra_response, "data", []))
                if not extra_images:
                    break

                responses.append(extra_response)
                images.extend(extra_images)
                attempts += 1

            images = images[:n]
            usage_metadata = merge_usage_metadata(*responses)
            image_count = len(images)
            for image_data in images:
                if not image_data.b64_json:
                    continue

                try:
                    mime_type, blob_image = decode_image(image_data.b64_json)
                    metadata = {"mime_type": mime_type, **usage_metadata}
                    yield self.create_blob_message(blob=blob_image, meta=metadata)
                except Exception:
                    yield self.create_text_message("Error processing an edited image in the Azure response.")
                    continue

            yield self.create_variable_message("requested_n", n)
            yield self.create_variable_message("actual_image_count", image_count)
            yield self.create_variable_message("fallback_used", fallback_used)

            usage_output = build_usage_output_from_metadata(
                usage_metadata=usage_metadata,
                model=deployment_name,
                operation="edit",
                image_count=image_count,
                requested_n=n,
                fallback_used=fallback_used,
            )
            if usage_output:
                yield self.create_json_message(usage_output)
        except Exception:
            yield self.create_text_message("Error processing the Azure image edit response.")
            return

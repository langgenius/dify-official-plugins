from collections.abc import Generator
from typing import Any, Dict

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from openai import AzureOpenAI

from tools._image_utils import (
    build_usage_output_from_metadata,
    decode_image,
    is_size_string,
    merge_usage_metadata,
)


class GPTImage2GenerateTool(Tool):
    def _invoke(
        self, tool_parameters: dict
    ) -> Generator[ToolInvokeMessage, None, None]:
        deployment_name = self.runtime.credentials["azure_openai_api_model_name"]
        client = AzureOpenAI(
            api_key=self.runtime.credentials["azure_openai_api_key"],
            azure_endpoint=self.runtime.credentials["azure_openai_base_url"],
            api_version=self.runtime.credentials["azure_openai_api_version"],
        )

        prompt = tool_parameters.get("prompt", "")
        if not prompt:
            yield self.create_text_message("Please input prompt")
            return

        generation_args: Dict[str, Any] = {
            "model": deployment_name,
            "prompt": prompt,
        }

        size = tool_parameters.get("size", "1024x1024")
        if not isinstance(size, str) or not is_size_string(size):
            yield self.create_text_message("Invalid size. Use a WxH string such as 1024x1024 or 1536x1024.")
            return
        generation_args["size"] = size

        quality = tool_parameters.get("quality", "high")
        if quality not in {"low", "medium", "high"}:
            yield self.create_text_message("Invalid quality. Choose low, medium, or high.")
            return
        generation_args["quality"] = quality

        output_format = tool_parameters.get("output_format", "png")
        if output_format not in {"png", "jpeg"}:
            yield self.create_text_message("Invalid output_format. Choose png or jpeg.")
            return
        generation_args["output_format"] = output_format

        output_compression = tool_parameters.get("output_compression", 100)
        try:
            output_compression = int(output_compression)
        except (TypeError, ValueError):
            yield self.create_text_message("Invalid output_compression. Choose an integer between 0 and 100.")
            return

        if not 0 <= output_compression <= 100:
            yield self.create_text_message("Invalid output_compression. Choose an integer between 0 and 100.")
            return

        if output_format == "jpeg":
            generation_args["output_compression"] = output_compression

        n_str = tool_parameters.get("n")
        n = 1
        if n_str is not None:
            try:
                n = int(n_str)
                if not 1 <= n <= 10:
                    raise ValueError("Number of images (n) must be between 1 and 10.")
            except ValueError as e:
                yield self.create_text_message(f"Invalid n: {e}")
                return
        generation_args["n"] = n

        try:
            response = client.images.generate(**generation_args)
        except Exception:
            yield self.create_text_message(
                "Failed to generate image. Check the Azure OpenAI deployment, API version, and request parameters."
            )
            return

        responses = [response]
        images = list(getattr(response, "data", []))
        fallback_used = False
        attempts = 1

        while len(images) < n and attempts < n:
            remaining = n - len(images)
            fallback_used = True
            fallback_args = dict(generation_args)
            fallback_args["n"] = remaining
            try:
                extra_response = client.images.generate(**fallback_args)
            except Exception:
                break

            extra_images = list(getattr(extra_response, "data", []))
            if not extra_images:
                break

            responses.append(extra_response)
            images.extend(extra_images)
            attempts += 1

        images = images[:n]
        usage_metadata = merge_usage_metadata(*responses)
        image_count = len(images)

        for image in images:
            if not image.b64_json:
                continue
            mime_type, blob_image = decode_image(image.b64_json)
            final_mime_type = f"image/{output_format}" if output_format in {"png", "jpeg"} else mime_type

            metadata = {"mime_type": final_mime_type, **usage_metadata}
            yield self.create_blob_message(blob=blob_image, meta=metadata)

        yield self.create_variable_message("requested_n", n)
        yield self.create_variable_message("actual_image_count", image_count)
        yield self.create_variable_message("fallback_used", fallback_used)

        usage_output = build_usage_output_from_metadata(
            usage_metadata=usage_metadata,
            model=deployment_name,
            operation="generate",
            image_count=image_count,
            requested_n=n,
            fallback_used=fallback_used,
        )
        if usage_output:
            yield self.create_json_message(usage_output)

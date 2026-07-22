import base64
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError
from openai import OpenAI


class MaiImageTool(Tool):
    DEFAULT_BASE_URL = "https://api.inferera.com"

    def get_base_url(self) -> str:
        return (self.runtime.credentials.get("base_url") or self.DEFAULT_BASE_URL).rstrip("/")

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            prompt = str(tool_parameters.get("prompt") or "").strip()
            if not prompt:
                raise InvokeError("Prompt is required")
            model = str(tool_parameters.get("model") or "mai-image-2.5-flash")
            if model not in {"mai-image-2.5-flash", "mai-image-2.5"}:
                raise InvokeError("Unsupported MAI Image model")

            api_key = self.runtime.credentials.get("api_key")
            if not api_key:
                raise InvokeError("API Key is required")

            yield self.create_text_message(f"Generating image with {model}...")
            client = OpenAI(
                api_key=api_key,
                base_url=f"{self.get_base_url()}/v1",
                timeout=180,
            )
            response = client.images.generate(model=model, prompt=prompt)
            images = list(response.data or [])
            if not images:
                raise InvokeError("No images were generated")

            emitted = 0
            for index, item in enumerate(images, start=1):
                encoded = getattr(item, "b64_json", None)
                url = getattr(item, "url", None)
                if encoded:
                    yield self.create_blob_message(
                        blob=base64.b64decode(encoded),
                        meta={"mime_type": "image/png", "filename": f"mai_image_{index}.png"},
                    )
                    emitted += 1
                elif url:
                    yield self.create_image_message(url)
                    emitted += 1

            if not emitted:
                raise InvokeError("Image response contained neither base64 data nor URL")
            yield self.create_json_message({"success": True, "model": model, "num_images": emitted})
        except InvokeError:
            raise
        except Exception as exc:
            raise InvokeError(f"MAI Image generation failed: {exc}") from exc

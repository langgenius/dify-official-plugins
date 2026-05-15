import base64
import requests
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError


class WanTool(Tool):
    BASE_URL = "https://aihubmix.com/v1"

    def get_endpoint(self, model: str) -> str:
        return f"{self.BASE_URL}/models/bailian/{model}/predictions"

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            prompt = tool_parameters.get("prompt", "").strip()
            if not prompt:
                raise InvokeError("Prompt is required")

            model = tool_parameters.get("model", "wan2.7-image-pro")
            size = tool_parameters.get("size", "2K")
            n = int(tool_parameters.get("n", 1))
            thinking_mode = tool_parameters.get("thinking_mode", True)
            seed = tool_parameters.get("seed")
            watermark = tool_parameters.get("watermark", False)

            api_key = self.runtime.credentials.get("api_key")
            if not api_key:
                raise InvokeError("API Key is required")

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }

            inputs: dict[str, Any] = {
                "prompt": prompt,
                "size": size,
                "n": n,
                "thinking_mode": thinking_mode,
                "watermark": watermark,
            }
            if seed is not None:
                inputs["seed"] = int(seed)

            payload = {"input": inputs}

            yield self.create_text_message(f"Generating {n} image(s) with {model} ({size})...")

            response = requests.post(
                self.get_endpoint(model),
                headers=headers,
                json=payload,
                timeout=300,
            )

            if response.status_code != 200:
                error_msg = f"Wan API request failed with status {response.status_code}"
                try:
                    error_data = response.json()
                    if "error" in error_data:
                        error_msg += f": {error_data['error'].get('message', 'Unknown error')}"
                except Exception:
                    pass
                raise InvokeError(error_msg)

            data = response.json()

            images: list[dict[str, str]] = []
            output = data.get("output")
            if isinstance(output, list):
                for item in output:
                    if isinstance(item, dict):
                        if "b64_json" in item:
                            images.append({"b64_json": item["b64_json"]})
                        elif "url" in item:
                            images.append({"url": item["url"]})

            if not images:
                raise InvokeError("No images were generated")

            for idx, img in enumerate(images):
                if "b64_json" in img:
                    image_bytes = base64.b64decode(img["b64_json"])
                    yield self.create_blob_message(
                        blob=image_bytes,
                        meta={"mime_type": "image/png", "filename": f"wan_{idx + 1}.png"},
                    )
                elif "url" in img:
                    yield self.create_image_message(img["url"])

            yield self.create_json_message({
                "success": True,
                "model": model,
                "prompt": prompt,
                "size": size,
                "num_images": len(images),
                "images": images,
                "watermark": watermark,
            })

            image_urls = "\n".join(img["url"] for img in images if "url" in img)
            if image_urls:
                yield self.create_text_message(image_urls)

        except InvokeError:
            raise
        except Exception as e:
            raise InvokeError(f"Wan image generation failed: {e}")

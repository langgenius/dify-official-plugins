import base64
import requests
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError


class IdeogramTool(Tool):
    BASE_URL = "https://aihubmix.com/v1"
    ENDPOINT = f"{BASE_URL}/models/ideogram/V3/predictions"

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            prompt = tool_parameters.get("prompt", "").strip()
            if not prompt:
                raise InvokeError("Prompt is required")

            rendering_speed = tool_parameters.get("rendering_speed", "QUALITY")
            aspect_ratio = tool_parameters.get("aspect_ratio", "1x1")

            api_key = self.runtime.credentials.get("api_key")
            if not api_key:
                raise InvokeError("API Key is required")

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "input": {
                    "prompt": prompt,
                    "rendering_speed": rendering_speed,
                    "aspect_ratio": aspect_ratio,
                }
            }

            yield self.create_text_message(
                f"Generating image with Ideogram V3 ({rendering_speed}, {aspect_ratio})..."
            )

            response = requests.post(self.ENDPOINT, headers=headers, json=payload, timeout=120)

            if response.status_code != 200:
                error_msg = f"Ideogram API request failed with status {response.status_code}"
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
                        meta={"mime_type": "image/png", "filename": f"ideogram_{idx + 1}.png"},
                    )
                elif "url" in img:
                    yield self.create_image_message(img["url"])

            yield self.create_json_message({
                "success": True,
                "model": "ideogram/V3",
                "prompt": prompt,
                "rendering_speed": rendering_speed,
                "aspect_ratio": aspect_ratio,
                "num_images": len(images),
                "images": images,
            })

            image_urls = "\n".join(img["url"] for img in images if "url" in img)
            if image_urls:
                yield self.create_text_message(image_urls)

        except InvokeError:
            raise
        except Exception as e:
            raise InvokeError(f"Ideogram image generation failed: {e}")

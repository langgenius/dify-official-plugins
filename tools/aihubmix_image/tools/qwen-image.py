import base64
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.model import InvokeError


QWEN_IMAGE_3_MODELS = {"qwen-image-3.0", "qwen-image-3.0-pro"}


def endpoint_path(model: str) -> str:
    if model in QWEN_IMAGE_3_MODELS:
        return "/ai/v1/images/generations"
    vendor = "qianfan" if model == "qwen-image" else "bailian"
    return f"/v1/models/{vendor}/{model}/predictions"


def build_payload(
    *,
    model: str,
    prompt: str,
    resolution: str,
    num_images: int,
    refer_image: str,
    guidance: float,
    watermark: bool,
    image_format: str,
) -> dict[str, Any]:
    if model in QWEN_IMAGE_3_MODELS:
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "n": num_images,
            "size": resolution,
        }
        if image_format:
            payload["output_format"] = image_format
        if refer_image:
            payload["image"] = refer_image
        if watermark:
            payload["extra"] = {"watermark": True}
        return payload

    return {
        "input": {
            "prompt": prompt,
            "refer_image": refer_image,
            "n": num_images,
            "size": resolution,
            "guidance": guidance,
            "watermark": watermark,
        }
    }


def extract_images(data: dict[str, Any]) -> list[dict[str, str]]:
    items: Any = data.get("data")
    if not isinstance(items, list):
        items = data.get("output")

    if isinstance(items, dict):
        items = items.get("b64_json") or items.get("images") or []
    if not isinstance(items, list):
        return []

    images: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("content_url"), str):
            images.append({"content_url": item["content_url"]})
            continue
        if isinstance(item.get("url"), str):
            images.append({"url": item["url"]})
            continue
        for key in ("b64_json", "bytesBase64", "bytesBase64Encoded"):
            value = item.get(key)
            if isinstance(value, str):
                images.append({"b64_json": value})
                break
    return images


def detect_image_format(image_bytes: bytes) -> tuple[str, str]:
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return "image/webp", "webp"
    return "image/png", "png"


def download_protected_image(content_url: str, api_key: str) -> bytes:
    response = requests.get(
        content_url,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=120,
    )
    if response.status_code != 200:
        raise InvokeError(
            f"Qwen Image result download failed with status {response.status_code}"
        )
    return response.content


class QwenImageTool(Tool):
    """Generate images with the Qwen Image family."""

    DEFAULT_BASE_URL = "https://api.inferera.com"

    def get_base_url(self) -> str:
        return (self.runtime.credentials.get("base_url") or self.DEFAULT_BASE_URL).rstrip("/")

    def get_endpoint(self, model: str) -> str:
        return f"{self.get_base_url()}{endpoint_path(model)}"

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            prompt = tool_parameters.get("prompt", "").strip()
            if not prompt:
                raise InvokeError("Prompt is required")

            model = tool_parameters.get("model", "qwen-image")
            resolution = tool_parameters.get("resolution", "1024x1024")
            num_images = int(tool_parameters.get("num_images", 1))
            refer_image = tool_parameters.get("refer_image", "")
            guidance = float(tool_parameters.get("guidance", 7.5))
            watermark = tool_parameters.get("watermark", False)
            image_format = tool_parameters.get("image_format", "png")

            if num_images < 1 or num_images > 4:
                raise InvokeError("Number of images must be between 1 and 4")

            api_key = self.runtime.credentials.get("api_key")
            if not api_key:
                raise InvokeError("API Key is required")

            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = build_payload(
                model=model,
                prompt=prompt,
                resolution=resolution,
                num_images=num_images,
                refer_image=refer_image,
                guidance=guidance,
                watermark=watermark,
                image_format=image_format,
            )

            yield self.create_text_message(f"Generating {num_images} image(s) with {model}...")

            response = requests.post(
                self.get_endpoint(model),
                headers=headers,
                json=payload,
                timeout=300,
            )
            if response.status_code != 200:
                error_msg = f"Qwen Image API request failed with status {response.status_code}"
                try:
                    error = response.json().get("error")
                    if isinstance(error, dict):
                        error_msg += f": {error.get('message', 'Unknown error')}"
                    elif error:
                        error_msg += f": {error}"
                except ValueError:
                    pass
                raise InvokeError(error_msg)

            response_data = response.json()
            images = extract_images(response_data)
            if not images:
                raise InvokeError("No images were generated")

            for idx, image in enumerate(images):
                if "b64_json" in image:
                    image_bytes = base64.b64decode(image["b64_json"])
                    mime_type, extension = detect_image_format(image_bytes)
                    yield self.create_blob_message(
                        blob=image_bytes,
                        meta={
                            "mime_type": mime_type,
                            "filename": f"qwen_image_{idx + 1}.{extension}",
                        },
                    )
                elif "url" in image:
                    yield self.create_image_message(image["url"])
                elif "content_url" in image:
                    image_bytes = download_protected_image(image["content_url"], api_key)
                    mime_type, extension = detect_image_format(image_bytes)
                    yield self.create_blob_message(
                        blob=image_bytes,
                        meta={
                            "mime_type": mime_type,
                            "filename": f"qwen_image_{idx + 1}.{extension}",
                        },
                    )

            yield self.create_json_message(
                {
                    "success": True,
                    "model": model,
                    "prompt": prompt,
                    "resolution": resolution,
                    "num_images": len(images),
                    "images": images,
                    "refer_image": refer_image,
                    "guidance": guidance,
                    "watermark": watermark,
                    "image_format": image_format,
                    "task_id": response_data.get("id"),
                }
            )

            image_urls = "\n".join(image["url"] for image in images if "url" in image)
            if image_urls:
                yield self.create_text_message(image_urls)
        except InvokeError:
            raise
        except Exception as exc:
            raise InvokeError(f"Qwen Image generation failed: {exc}") from exc

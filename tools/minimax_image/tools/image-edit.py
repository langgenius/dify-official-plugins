import base64
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from utils import MODEL, emit_images


def _as_items(value: Any) -> list[Any]:
    if not value:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _image_url(image: Any) -> str:
    if isinstance(image, str):
        return image
    blob = getattr(image, "blob", None)
    if blob:
        mime = getattr(image, "mime_type", None) or "image/png"
        return f"data:{mime};base64,{base64.b64encode(blob).decode('ascii')}"
    url = getattr(image, "url", None)
    if isinstance(url, str) and url:
        return url
    raise ValueError("unsupported image input")


class ImageEditTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        prompt = str(tool_parameters.get("prompt") or "").strip()
        if not prompt:
            yield self.create_text_message("Error: prompt is required")
            return

        images = _as_items(tool_parameters.get("images"))
        if not images:
            yield self.create_text_message("Error: images is required for image editing")
            return
        if len(images) > 16:
            yield self.create_text_message("Error: at most 16 reference images are supported")
            return

        yield from emit_images(
            self,
            self.runtime.credentials,
            "/v1/images/edits",
            {
                "model": MODEL,
                "prompt": prompt,
                "aspect_ratio": tool_parameters.get("aspect_ratio") or "1:1",
                "area": tool_parameters.get("area") or "1K",
                "images": [{"image_url": _image_url(image)} for image in images],
            },
        )

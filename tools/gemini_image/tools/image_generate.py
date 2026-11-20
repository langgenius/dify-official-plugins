import base64
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ImageGenerateTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        prompt = tool_parameters.get("prompt")
        if not prompt:
            yield self.create_text_message("Please input prompt")
            return

        model = tool_parameters.get("model", "gemini-2.5-flash-image")
        nano_banana_21 = model == "gemini-nano-banana-2.1"
        images = tool_parameters.get("images") or []
        if not isinstance(images, list):
            images = [images]
        if nano_banana_21 or model == "gemini-3-pro-image-preview":
            if len(images) > 14:
                yield self.create_text_message("Use at most 14 reference images.")
                return
        elif len(images) > 3:
            yield self.create_text_message("Warning: The number of input images should be three or less.")

        parts = [{"text": prompt}]
        for image in images:
            parts.append(
                {
                    "inlineData": {
                        "mimeType": image.mime_type,
                        "data": base64.b64encode(image.blob).decode("ascii"),
                    }
                }
            )
        body = {"contents": [{"parts": parts}]}
        image_config = {}
        size = tool_parameters.get("image_size")
        if size and size != "auto":
            if model == "gemini-2.5-flash-image" or size not in ("1K", "2K", "4K"):
                yield self.create_text_message(
                    "Image size requires Nano Banana Pro or 2.1 and a value of 1K, 2K, or 4K."
                )
                return
            image_config["imageSize"] = size
        ratio = tool_parameters.get("aspect_ratio")
        if ratio and ratio != "auto":
            if not nano_banana_21 and ratio in ("1:4", "4:1", "1:8", "8:1"):
                yield self.create_text_message("This aspect ratio requires Nano Banana 2.1.")
                return
            image_config["aspectRatio"] = ratio
        if image_config:
            body["generationConfig"] = {"imageConfig": image_config}

        version = "v1" if nano_banana_21 else "v1beta"
        response = requests.post(
            f"https://generativelanguage.googleapis.com/{version}/models/{model}:generateContent",
            headers={"x-goog-api-key": self.runtime.credentials["gemini_api_key"]},
            json=body,
            timeout=(5, 300),
        )
        result = response.json()
        if "error" in result:
            raise ValueError(result["error"]["message"])
        response.raise_for_status()

        files = []
        for candidate in result.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if part.get("thought"):
                    continue
                if part.get("text"):
                    yield self.create_text_message(text=part["text"])
                data = part.get("inlineData")
                if data and data.get("data"):
                    files.append(data)
        for index, data in enumerate(files):
            mime = data.get("mimeType", "image/png")
            extension = mime.rsplit("/", 1)[-1]
            yield self.create_blob_message(
                blob=base64.b64decode(data["data"]),
                meta={"filename": f"output{index}.{extension}", "mime_type": mime},
            )

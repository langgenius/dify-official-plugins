import base64
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ImageGenerateTool(Tool):
    def _invoke(
        self,
        tool_parameters: dict[str, Any],
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        self._gemini_api_key = self.runtime.credentials["gemini_api_key"]

        prompt = tool_parameters.get("prompt", "")
        if not prompt:
            yield self.create_text_message("Please input prompt")
            return
        model = tool_parameters.get("model", "gemini-2.5-flash-image-preview")
        images = tool_parameters.get("images", [])
        if not isinstance(images, list):
            images = [images]  # Make one image to list
        generated_blobs = []
        if len(images) == 0:
            generated_blobs = self.txt2img(prompt)
        else:
            for image in images:
                generated_blobs += self.img2img(prompt, image.blob, image.mime_type)
        for i, blob in enumerate(generated_blobs):
            yield self.create_blob_message(
                blob=blob,
                meta={
                    "filename": f"output{i}.png",
                    "mime_type": "image/png",
                },
            )

    def txt2img(self, prompt: str) -> list[bytes]:
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image-preview:generateContent"
        data = {"contents": [{"parts": [{"text": prompt}]}]}
        headers = {"x-goog-api-key": self._gemini_api_key, "Content-Type": "application/json"}
        response = requests.post(url, json=data, headers=headers).json()
        if "error" in response:
            raise Exception(response["error"]["message"])

        image_blobs = []
        for candidate in response.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                inline_data = part.get("inlineData")
                if inline_data and "data" in inline_data:
                    image_blobs.append(base64.b64decode(inline_data["data"]))
        return image_blobs

    def img2img(self, prompt: str, image_blob: bytes, mime_type: str) -> list[bytes]:
        input_base64 = base64.b64encode(image_blob).decode()
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image-preview:generateContent"
        data = {
            "contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": mime_type, "data": input_base64}}]}]
        }
        headers = {"x-goog-api-key": self._gemini_api_key, "Content-Type": "application/json"}
        response = requests.post(url, json=data, headers=headers).json()
        if "error" in response:
            raise Exception(response["error"]["message"])

        image_blobs = []
        for candidate in response.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                inline_data = part.get("inlineData")
                if inline_data and "data" in inline_data:
                    image_blobs.append(base64.b64decode(inline_data["data"]))
        return image_blobs

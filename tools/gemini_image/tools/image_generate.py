import base64
from collections.abc import Generator
from typing import Any

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class ImageGenerateTool(Tool):
    _BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

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
        model = tool_parameters.get("model", "gemini-2.5-flash-image")
        images = tool_parameters.get("images", [])
        if not isinstance(images, list):
            images = [images]  # Make one image to list

        generated_blobs: list[bytes] = []
        generated_texts: list[str] = []
        if len(images) == 0:
            generated_blobs, generated_texts = self.txt2img(prompt, model)
        else:
            if len(images) > 3:
                # https://ai.google.dev/gemini-api/docs/image-generation#limitations
                yield self.create_text_message("Warning: The number of input images should be three or less.")
            generated_blobs, generated_texts = self.img2img(prompt, [img.blob for img in images], [img.mime_type for img in images], model)

        for text in generated_texts:
            yield self.create_text_message(text=text)

        for i, blob in enumerate(generated_blobs):
            yield self.create_blob_message(
                blob=blob,
                meta={
                    "filename": f"output{i}.png",
                    "mime_type": "image/png",
                },
            )

    def txt2img(self, prompt: str, model: str) -> tuple[list[bytes], list[str]]:
        url = f"{self._BASE_URL}/{model}:generateContent"
        headers = {"x-goog-api-key": self._gemini_api_key,
                   "Content-Type": "application/json"}

        response = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}]}, headers=headers, timeout=(5, 300)).json()
        if "error" in response:
            raise Exception(response["error"]["message"])

        image_blobs: list[bytes] = []
        texts: list[str] = []
        for candidate in response.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                text = part.get("text")
                if text:
                    texts.append(text)
                inline_data = part.get("inlineData")
                if inline_data and "data" in inline_data:
                    image_blobs.append(base64.b64decode(inline_data["data"]))
        return image_blobs, texts

    def img2img(self, prompt: str, image_blobs: list[bytes], mime_types: list[str], model: str) -> tuple[list[bytes], list[str]]:
        if len(image_blobs) != len(mime_types):
            raise Exception("Number of image_blobs and mime_types does not match!")
        url = f"{self._BASE_URL}/{model}:generateContent"
        headers = {"x-goog-api-key": self._gemini_api_key, "Content-Type": "application/json"}
        parts = [{"text": prompt}]
        for i in range(len(image_blobs)):
            input_base64 = base64.b64encode(image_blobs[i]).decode()
            parts.append({"inline_data": {"mime_type": mime_types[i], "data": input_base64}})

        response = requests.post(url, json={"contents": [{"parts": parts}]}, headers=headers, timeout=(5, 300)).json()
        if "error" in response:
            raise Exception(response["error"]["message"])

        image_blobs: list[bytes] = []
        texts: list[str] = []
        for candidate in response.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                text = part.get("text")
                if text:
                    texts.append(text)
                inline_data = part.get("inlineData")
                if inline_data and "data" in inline_data:
                    image_blobs.append(base64.b64decode(inline_data["data"]))
        return image_blobs, texts

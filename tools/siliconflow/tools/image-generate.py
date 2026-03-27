from typing import Any, Generator

import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

SILICONFLOW_IMAGE_API_URL = "https://api.siliconflow.cn/v1/images/generations"
REQUEST_TIMEOUT = 120
IMAGE_GENERATION_MODELS = {
    "kolors": "Kwai-Kolors/Kolors",
    "qwen_image": "Qwen/Qwen-Image",
}


class ImageGenerateTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        prompt = str(tool_parameters.get("prompt", "")).strip()
        if not prompt:
            yield self.create_text_message("Error: prompt is required")
            return

        model_key = tool_parameters.get("model", "kolors")
        model = IMAGE_GENERATION_MODELS.get(model_key)
        if not model:
            yield self.create_text_message("Error: unsupported image generation model")
            return

        payload = {
            "model": model,
            "prompt": prompt,
            "negative_prompt": tool_parameters.get("negative_prompt"),
            "seed": tool_parameters.get("seed"),
            "num_inference_steps": tool_parameters.get("num_inference_steps", 20),
            "image": tool_parameters.get("image"),
        }

        if model == "Kwai-Kolors/Kolors":
            payload["image_size"] = tool_parameters.get("image_size", "1024x1024")
            payload["batch_size"] = tool_parameters.get("batch_size", 1)
            payload["guidance_scale"] = tool_parameters.get("guidance_scale", 7.5)
        else:
            payload["image_size"] = tool_parameters.get("image_size", "1328x1328")
            payload["cfg"] = tool_parameters.get("cfg", 4)

        payload = {
            key: value for key, value in payload.items() if value not in (None, "")
        }

        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Bearer {self.runtime.credentials['siliconFlow_api_key']}",
        }

        try:
            response = requests.post(
                SILICONFLOW_IMAGE_API_URL,
                json=payload,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
        except requests.RequestException as exc:
            yield self.create_text_message(
                f"Failed to call SiliconFlow image API: {exc}"
            )
            return

        if response.status_code != 200:
            yield self.create_text_message(f"Got Error Response: {response.text}")
            return

        res = response.json()
        yield self.create_json_message(res)
        for image in res.get("images", []):
            image_url = image.get("url")
            if image_url:
                yield self.create_image_message(image_url)

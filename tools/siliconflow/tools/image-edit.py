from typing import Any, Generator

import requests

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

SILICONFLOW_IMAGE_API_URL = "https://api.siliconflow.cn/v1/images/generations"
QWEN_IMAGE_EDIT_MODELS = {
    "qwen_image_edit_2509": "Qwen/Qwen-Image-Edit-2509",
    "qwen_image_edit": "Qwen/Qwen-Image-Edit",
}
REQUEST_TIMEOUT = 120


class ImageEditTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        prompt = str(tool_parameters.get("prompt", "")).strip()
        if not prompt:
            yield self.create_text_message("Error: prompt is required")
            return

        if not tool_parameters.get("image"):
            yield self.create_text_message("Error: image is required for image editing")
            return

        model_key = tool_parameters.get("model", "qwen_image_edit_2509")
        model = QWEN_IMAGE_EDIT_MODELS.get(model_key)
        if not model:
            yield self.create_text_message("Error: unsupported image edit model")
            return

        if model != "Qwen/Qwen-Image-Edit-2509" and any(
            tool_parameters.get(field) not in (None, "")
            for field in ("image2", "image3")
        ):
            yield self.create_text_message(
                "Error: image2 and image3 are only supported by Qwen/Qwen-Image-Edit-2509"
            )
            return

        payload = {
            "model": model,
            "prompt": prompt,
            "seed": tool_parameters.get("seed"),
            "num_inference_steps": tool_parameters.get("num_inference_steps", 20),
            "cfg": tool_parameters.get("cfg", 4),
            "image": tool_parameters.get("image"),
        }

        if model == "Qwen/Qwen-Image-Edit-2509":
            payload["image2"] = tool_parameters.get("image2")
            payload["image3"] = tool_parameters.get("image3")

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

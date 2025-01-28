from typing import Any, Generator
import requests
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool

SILICONFLOW_API_URL = "https://api.siliconflow.cn/v1/image/generations"
FLUX_MODELS = {
    "FLUX.1-schnell": "black-forest-labs/FLUX.1-schnell",
    "FLUX.1-dev": "black-forest-labs/FLUX.1-dev",
    "FLUX.1-pro": "black-forest-labs/FLUX.1-pro",
}

class FluxTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Bearer {self.runtime.credentials['siliconFlow_api_key']}",
        }
        model = tool_parameters.get("model", "FLUX.1-schnell")
        flux_model = FLUX_MODELS.get(model)
        payload = {
            "model": flux_model,
            "prompt": tool_parameters.get("prompt"),
            "image_size": tool_parameters.get("image_size", "1024x1024"),
            "seed": tool_parameters.get("seed"),
            "num_inference_steps": tool_parameters.get("num_inference_steps", 4),
        }
        response = requests.post(SILICONFLOW_API_URL, json=payload, headers=headers)
        if response.status_code != 200:
            yield self.create_text_message(f"Got Error Response:{response.text}")
        res = response.json()
        yield self.create_json_message(res)
        for image in res.get("images", []):
            yield self.create_image_message(image.get("url"))

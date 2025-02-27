from typing import Any, Generator
import requests
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool

SILICONFLOW_API_URL = "https://api.siliconflow.cn/v1/image/generations"
Janus_MODELS = {
    "Janus-Pro-7B": "deepseek-ai/Janus-Pro-7B",
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
        model = tool_parameters.get("model", "Janus-Pro-7B")
        flux_model = Janus_MODELS.get(model)
        payload = {
            "model": flux_model,
            "prompt": tool_parameters.get("prompt"),
            "seed": tool_parameters.get("seed"),
        }
        response = requests.post(SILICONFLOW_API_URL, json=payload, headers=headers)
        if response.status_code != 200:
            yield self.create_text_message(f"Got Error Response:{response.text}")
        res = response.json()
        yield self.create_json_message(res)
        for image in res.get("images", []):
            yield self.create_image_message(image.get("url"))

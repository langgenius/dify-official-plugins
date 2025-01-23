from typing import Any, Generator
import requests
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool

SILICONFLOW_API_URL = "https://api.siliconflow.cn/v1/image/generations"
SD_MODELS = {
    "sd_3.5_large": "stabilityai/stable-diffusion-3-5-large",
    "sd_3.5_large_turbo": "stabilityai/stable-diffusion-3-5-large-turbo",
}


class StableDiffusionTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "authorization": f"Bearer {self.runtime.credentials['siliconFlow_api_key']}",
        }
        model = tool_parameters.get("model", "sd_3.5_large_turbo")
        sd_model = SD_MODELS.get(model)
        payload = {
            "model": sd_model,
            "prompt": tool_parameters.get("prompt"),
            "negative_prompt": tool_parameters.get("negative_prompt", ""),
            "image_size": tool_parameters.get("image_size", "1024x1024"),
            "batch_size": tool_parameters.get("batch_size", 1),
            "seed": tool_parameters.get("seed"),
            "guidance_scale": tool_parameters.get("guidance_scale", 7.5),
            "num_inference_steps": tool_parameters.get("num_inference_steps", 4),
        }
        response = requests.post(SILICONFLOW_API_URL, json=payload, headers=headers)
        if response.status_code != 200:
            yield self.create_text_message(f"Got Error Response:{response.text}")
        res = response.json()
        # result = [self.create_json_message(res)]
        yield self.create_json_message(res)
        for image in res.get("images", []):
            yield self.create_image_message(image.get("url"))
        #     result.append(self.create_image_message(image=image.get("url"), save_as=self.VariableKey.IMAGE.value))
        # yield result

from typing import Any
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from tools.novitaai_txt2img import NovitaAiTxt2ImgTool
from dify_plugin import ToolProvider


class NovitaAIProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            for _ in NovitaAiTxt2ImgTool.from_credentials(credentials).invoke(
                tool_parameters={
                    "model_name": "cinenautXLATRUE_cinenautV10_392434.safetensors",
                    "prompt": "a futuristic city with flying cars",
                    "negative_prompt": "",
                    "width": 128,
                    "height": 128,
                    "image_num": 1,
                    "guidance_scale": 7.5,
                    "seed": -1,
                    "steps": 1,
                }
            ):
                pass
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))

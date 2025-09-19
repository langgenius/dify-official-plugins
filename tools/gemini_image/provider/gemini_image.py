from typing import Any

from dify_plugin import ToolProvider
from tools.image_generate import ImageGenerateTool
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class GeminiImageProvider(ToolProvider):
    def _validate_credentials(self,  credentials: dict[str, Any]) -> None:
        try:
            for _ in ImageGenerateTool.from_credentials(credentials, user_id="").invoke(
                tool_parameters={
                    "prompt": "cute girl, blue eyes, white hair, anime style",
                    "model": "gemini-2.5-flash-image-preview",
                    "num": 1,
                }                
            ):
                pass
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))
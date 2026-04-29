from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from tools.image_generate import ImageGenerateTool


class AzureOpenAIProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            for _ in ImageGenerateTool.from_credentials(credentials, user_id="").invoke(
                tool_parameters={"prompt": "cute girl, blue eyes, white hair, anime style", "size": "small", "n": 1}
            ):
                pass
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))

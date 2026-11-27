from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from tools.image_generate import ImageGenerateTool


class AzureOpenAIProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            messages = ImageGenerateTool.from_credentials(credentials, user_id="").invoke(
                tool_parameters={"prompt": "A blue square on a white background", "n": 1}
            )
            for message in messages:
                if message.type == message.MessageType.BLOB:
                    return
                if message.type == message.MessageType.TEXT:
                    raise ValueError(message.message.text)
            raise ValueError("Azure OpenAI did not return a generated image.")
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e)) from e

from typing import Any
from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from tools.tts import MinimaxTTS

class MinimaxTTSProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            for _ in MinimaxTTS.from_credentials(credentials).invoke(
                tool_parameters={"text": "test"}
            ):
                pass
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e)) 
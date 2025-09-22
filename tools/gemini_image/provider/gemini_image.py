from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class GeminiImageProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        if credentials.get("gemini_api_key") is None:
            raise ToolProviderCredentialValidationError("ERROR")

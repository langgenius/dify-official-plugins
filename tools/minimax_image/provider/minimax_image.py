from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class MiniMaxImageProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        if not str(credentials.get("api_key") or "").strip():
            raise ToolProviderCredentialValidationError("MiniMax API key is required")

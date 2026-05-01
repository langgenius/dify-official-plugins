from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class ErnieImageProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        if not (credentials.get("access_token") or "").strip():
            raise ToolProviderCredentialValidationError("Access token is required")

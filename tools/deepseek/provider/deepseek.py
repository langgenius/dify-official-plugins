from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from tools._client import DeepSeekClient


class DeepSeekProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            # Check authentication without issuing a billable search or fetch.
            DeepSeekClient(credentials).validate_credentials()
        except ValueError as exc:
            raise ToolProviderCredentialValidationError(str(exc)) from None

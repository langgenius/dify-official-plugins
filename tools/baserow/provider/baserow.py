from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from src.baserow import BaserowCredentials, BaserowPlugin


class BaserowProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            plugin = BaserowPlugin(credentials=BaserowCredentials(**credentials))
            plugin.verify()

        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))

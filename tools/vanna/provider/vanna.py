from typing import Any

import httpx2
from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from client.vanna import VannaClient


class VannaProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        if not credentials.get("api_key"):
            raise ToolProviderCredentialValidationError("Please input api key")
        try:
            with httpx2.Client(timeout=httpx2.Timeout(30, connect=10)) as http:
                VannaClient(
                    http, credentials["api_key"], endpoint=credentials.get("base_url")
                ).validate_credentials()
        except Exception as error:
            raise ToolProviderCredentialValidationError(str(error)) from error

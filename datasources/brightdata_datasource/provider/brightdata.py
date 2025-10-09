from typing import Any

from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin.interfaces.datasource import DatasourceProvider


class BrightdataProvider(DatasourceProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:

        api_token = credentials.get("api_token")

        # Basic validation only - no network calls
        if not api_token:
            raise ToolProviderCredentialValidationError(
                "Bright Data API token is required."
            )

        # Check if token has basic expected format
        api_token = str(api_token).strip()

        if len(api_token) < 10:
            raise ToolProviderCredentialValidationError(
                "API token appears too short to be valid."
            )

        pass

from typing import Any
import httpx

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from provider.endpoints import VALIDATE_API_KEY_ENDPOINT, AGENTQL_HOST_URL
from provider.messages import UNAUTHORIZED_ERROR_MESSAGE, INTERNAL_SERVER_ERROR_MESSAGE

class AgentQLProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        if "api_key" not in credentials or not credentials["api_key"]:
            raise ToolProviderCredentialValidationError("API Key is required.")

        validate_api_key_endpoint = f"{AGENTQL_HOST_URL}/{VALIDATE_API_KEY_ENDPOINT}"
        headers = {
            "X-API-Key": credentials["api_key"]
        }

        try:
            response = httpx.get(validate_api_key_endpoint, headers=headers)
            response.raise_for_status()

        except httpx.HTTPStatusError as e:
            response = e.response
            if response.status_code == httpx.codes.UNAUTHORIZED:
                raise ToolProviderCredentialValidationError(UNAUTHORIZED_ERROR_MESSAGE) from e
            elif response.status_code == httpx.codes.INTERNAL_SERVER_ERROR:
                raise ToolProviderCredentialValidationError(INTERNAL_SERVER_ERROR_MESSAGE) from e
            else:
                raise ToolProviderCredentialValidationError(f"HTTP {e}.") from e

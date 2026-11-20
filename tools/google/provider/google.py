from typing import Any

import requests
from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class GoogleProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        api_key = credentials.get("serpapi_api_key")
        if not api_key:
            raise ToolProviderCredentialValidationError("SerpAPI API key is required.")

        try:
            response = requests.get(
                "https://serpapi.com/account.json", params={"api_key": api_key}, timeout=10
            )
            if response.status_code == 200:
                account = response.json()
                if isinstance(account, dict) and account.get("account_id"):
                    return
        except Exception:  # noqa: BLE001 - the SDK sends the traceback to the caller
            raise ToolProviderCredentialValidationError("Could not verify the SerpAPI API key.") from None

        if response.status_code in (401, 403):
            raise ToolProviderCredentialValidationError("SerpAPI rejected the API key.")
        raise ToolProviderCredentialValidationError("SerpAPI did not return account details.")

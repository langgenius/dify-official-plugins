from typing import Any

import requests
from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class ShopSavvyProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        api_key = credentials.get("shopsavvy_api_key")
        if not api_key:
            raise ToolProviderCredentialValidationError("ShopSavvy API key is required.")

        base_url = credentials.get("base_url", "").strip()
        if not base_url:
            base_url = "https://api.shopsavvy.com/v1"

        try:
            response = requests.get(
                f"{base_url}/usage",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "User-Agent": "ShopSavvy-Dify/1.0",
                },
                timeout=15,
            )
            if not response.ok:
                raise ToolProviderCredentialValidationError(
                    f"ShopSavvy API returned {response.status_code}: {response.text}"
                )
        except requests.RequestException as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to connect to ShopSavvy API: {str(e)}"
            )

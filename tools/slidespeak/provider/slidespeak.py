from typing import Any
import httpx
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin import ToolProvider


class SlideSpeakProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        api_key = credentials.get("slidespeak_api_key")
        if not api_key:
            raise ToolProviderCredentialValidationError("API key is missing")

        # Use the same validation approach as the client
        headers = {"Content-Type": "application/json", "X-API-Key": api_key}

        url = "https://api.slidespeak.co/api/v1/me"
        with httpx.Client() as client:
            response = client.get(url, headers=headers)
        if response.status_code != 200:
            raise ToolProviderCredentialValidationError("Invalid SlideSpeak API key")

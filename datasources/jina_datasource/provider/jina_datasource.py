import json
from typing import Any

import requests
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin.interfaces.datasource import DatasourceProvider


class JinaProvider(DatasourceProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            api_key = credentials.get("api_key", "")
            if not api_key:
                raise ToolProviderCredentialValidationError("API key is required")
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }
            payload = {
                "url": "https://example.com",
            }
            response = requests.post(
                "https://r.jina.ai/", json=payload, headers=headers
            )
            if response.status_code == 200:
                return True
            else:
                raise ToolProviderCredentialValidationError("API key is invalid")
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))

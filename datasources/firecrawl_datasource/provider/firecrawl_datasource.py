from typing import Any, Mapping

import requests
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin.interfaces.datasource import DatasourceProvider


class FirecrawlDatasourceProvider(DatasourceProvider):
    def _validate_credentials(self, credentials: Mapping[str, Any]) -> None:
        try:
            api_key = credentials.get("firecrawl_api_key", "")
            if not api_key:
                raise ToolProviderCredentialValidationError("api key is required")

            base_url = credentials.get("base_url") or "https://api.firecrawl.dev"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }
            payload = {
                "url": "https://example.com",
                "includePaths": [],
                "excludePaths": [],
                "limit": 1,
                "scrapeOptions": {"onlyMainContent": True},
            }
            response = requests.post(
                f"{base_url}/v1/crawl", json=payload, headers=headers
            )
            if response.status_code == 200:
                return True
            else:
                raise ToolProviderCredentialValidationError("api key is invalid")

        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))

from collections.abc import Mapping
from typing import Any

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
                f"{base_url.rstrip('/')}/v2/crawl", json=payload, headers=headers
            )
            if response.status_code == 200:
                return True
            else:
                try:
                    response_data = response.json()
                except requests.exceptions.JSONDecodeError:
                    response_data = {}
                error = response_data.get("error") or response_data.get("message")
                raise ToolProviderCredentialValidationError(
                    error
                    or f"credential validation failed with status {response.status_code}"
                )

        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))

from collections.abc import Mapping
from typing import Any

import requests
from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class HackerNewsProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict) -> None:
        """
        Validate credentials for Hacker News provider.
        Since Hacker News API is free and public, no credentials are needed.
        """
        # No credentials needed for Hacker News API
        # Just verify that the API is accessible
        try:
            response = requests.get(
                "https://hacker-news.firebaseio.com/v0/topstories.json", timeout=10
            )
            if response.status_code != 200:
                raise ToolProviderCredentialValidationError(
                    "Unable to access Hacker News API"
                )
        except requests.RequestException as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to connect to Hacker News API: {str(e)}"
            )

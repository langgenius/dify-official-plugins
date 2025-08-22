from typing import Any, Mapping

import requests
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin.interfaces.datasource import DatasourceProvider

TAVILY_API_URL = "https://api.tavily.com"


class TavilyDatasourceProvider(DatasourceProvider):
    def _validate_credentials(self, credentials: Mapping[str, Any]) -> None:
        try:
            api_key = credentials.get("tavily_api_key", "")
            if not api_key:
                raise ToolProviderCredentialValidationError("Tavily API key is required")

            # Test the API key by performing a simple search
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            
            # Simple test search to validate API key
            payload = {
                "query": "test",
                "search_depth": "basic",
                "max_results": 1
            }
            
            response = requests.post(
                f"{TAVILY_API_URL}/search", 
                json=payload, 
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                return True
            elif response.status_code == 401:
                raise ToolProviderCredentialValidationError("Invalid Tavily API key")
            elif response.status_code == 429:
                raise ToolProviderCredentialValidationError("API rate limit exceeded. Please try again later.")
            else:
                raise ToolProviderCredentialValidationError(f"API validation failed with status {response.status_code}")

        except requests.exceptions.RequestException as e:
            raise ToolProviderCredentialValidationError(f"Failed to connect to Tavily API: {str(e)}")
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))
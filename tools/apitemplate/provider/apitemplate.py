from typing import Any
import requests

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class ApitemplateProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            api_key = credentials.get("api_key")
            if not api_key:
                raise ToolProviderCredentialValidationError("APITemplate.io API key is required.")
            
            # Test the API key by calling the account information endpoint
            headers = {
                "X-API-KEY": api_key,
                "Content-Type": "application/json"
            }
            
            response = requests.get(
                "https://rest.apitemplate.io/v2/account-information",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 401:
                raise ToolProviderCredentialValidationError("Invalid APITemplate.io API key.")
            elif response.status_code != 200:
                raise ToolProviderCredentialValidationError(f"Failed to validate API key: HTTP {response.status_code}")
                
            # Check if response contains expected data
            data = response.json()
            if data.get("status") != "success":
                raise ToolProviderCredentialValidationError("Invalid APITemplate.io API key or account access denied.")
                
        except requests.exceptions.RequestException as e:
            raise ToolProviderCredentialValidationError(f"Failed to connect to APITemplate.io: {str(e)}")
        except Exception as e:
            raise ToolProviderCredentialValidationError(f"Credential validation failed: {str(e)}")

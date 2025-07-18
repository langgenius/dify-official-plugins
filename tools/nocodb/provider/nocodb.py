from typing import Any
import requests

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class NocodbProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            # Get credentials
            nocodb_url = credentials.get("nocodb_url")
            api_token = credentials.get("nocodb_api_token")
            base_id = credentials.get("nocodb_base_id")
            
            # Validate required credentials
            if not nocodb_url:
                raise ToolProviderCredentialValidationError("NocoDB URL is required")
            if not api_token:
                raise ToolProviderCredentialValidationError("NocoDB API Token is required")
            if not base_id:
                raise ToolProviderCredentialValidationError("NocoDB Base ID is required")
            
            # Remove trailing slash from URL if present
            if nocodb_url.endswith("/"):
                nocodb_url = nocodb_url[:-1]
            
            # Test the connection by getting the list of tables in the base
            headers = {
                "xc-token": api_token,
                "Content-Type": "application/json"
            }
            
            # Try to fetch tables list to validate credentials
            response = requests.get(
                f"{nocodb_url}/api/v2/meta/bases/{base_id}/tables",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 401:
                raise ToolProviderCredentialValidationError("Invalid API token")
            elif response.status_code == 404:
                raise ToolProviderCredentialValidationError("Base ID not found or invalid")
            elif response.status_code != 200:
                raise ToolProviderCredentialValidationError(f"Failed to connect to NocoDB: HTTP {response.status_code}")
            
            # If we get here, credentials are valid
            
        except ToolProviderCredentialValidationError:
            raise
        except requests.exceptions.Timeout:
            raise ToolProviderCredentialValidationError("Connection timeout - please check your NocoDB URL")
        except requests.exceptions.ConnectionError:
            raise ToolProviderCredentialValidationError("Failed to connect to NocoDB - please check your URL")
        except Exception as e:
            raise ToolProviderCredentialValidationError(f"Failed to validate credentials: {str(e)}")

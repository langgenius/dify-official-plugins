from typing import Any
import requests

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from tools.notion_client import NotionClient


class NotionProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            # Check if integration_token is provided
            if "integration_token" not in credentials or not credentials.get("integration_token"):
                raise ToolProviderCredentialValidationError("Notion Integration Token is required.")
            
            # Try to authenticate with Notion API by making a test request
            integration_token = credentials.get("integration_token")
            
            try:
                # Initialize the Notion client and attempt to fetch the current user
                client = NotionClient(integration_token)
                # Make a request to the users endpoint to validate the token
                response = requests.get("https://api.notion.com/v1/users/me", headers=client.headers)
                
                if response.status_code == 401:
                    raise ToolProviderCredentialValidationError("Invalid Notion Integration Token.")
                elif response.status_code != 200:
                    raise ToolProviderCredentialValidationError(f"Failed to connect to Notion API: {response.status_code} {response.text}")
            except requests.RequestException as e:
                raise ToolProviderCredentialValidationError(f"Network error when connecting to Notion API: {str(e)}")
                
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))

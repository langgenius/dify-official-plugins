from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from hubspot import HubSpot
from hubspot.crm.contacts.exceptions import ApiException


class HubspotProvider(ToolProvider):
    """HubSpot Provider for Dify plugin integration."""
    
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """Validate HubSpot credentials by making a test API call.
        
        Args:
            credentials: Dictionary containing authentication credentials
                - access_token: HubSpot private app access token
                
        Raises:
            ToolProviderCredentialValidationError: If credentials are invalid
        """
        try:
            # Check if access_token is provided
            if "access_token" not in credentials or not credentials.get("access_token"):
                raise ToolProviderCredentialValidationError("HubSpot access token is required.")
            
            # Create HubSpot client
            client = HubSpot(access_token=credentials.get("access_token"))
            
            # Make a test API call to validate token
            # Get a single contact to verify API access (limit=1)
            client.crm.contacts.basic_api.get_page(limit=1)
            
        except ApiException as e:
            raise ToolProviderCredentialValidationError(f"Invalid HubSpot API token: {str(e)}")
        except Exception as e:
            raise ToolProviderCredentialValidationError(f"Failed to connect to HubSpot: {str(e)}")

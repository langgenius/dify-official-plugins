import requests
from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class AIHubMixImageProvider(ToolProvider):
    
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """
        Validate AIHubMix API Key by making a simple API call
        """
        api_key = credentials.get("api_key")
        if not api_key:
            raise ToolProviderCredentialValidationError("API Key is required")
        
        try:
            # Test API key with a simple request to AIHubMix API
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            # Use a simple model list endpoint to validate API key
            response = requests.get(
                "https://api.aihubmix.com/v1/models",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 401:
                raise ToolProviderCredentialValidationError("Invalid API Key")
            elif response.status_code != 200:
                raise ToolProviderCredentialValidationError(f"API validation failed: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            raise ToolProviderCredentialValidationError(f"Network error during validation: {str(e)}")
        except Exception as e:
            raise ToolProviderCredentialValidationError(f"Validation error: {str(e)}")

    #########################################################################################
    # OAuth support can be implemented by uncommenting the following functions.
    # Note: Ensure SDK version is 0.4.2 or higher for OAuth functionality.
    #########################################################################################
    # def _oauth_get_authorization_url(self, redirect_uri: str, system_credentials: Mapping[str, Any]) -> str:
    #     """
    #     Generate the authorization URL for aihubmix-image OAuth.
    #     """
    #     try:
    #         """
    #         IMPLEMENT YOUR AUTHORIZATION URL GENERATION HERE
    #         """
    #     except Exception as e:
    #         raise ToolProviderOAuthError(str(e))
    #     return ""
        
    # def _oauth_get_credentials(
    #     self, redirect_uri: str, system_credentials: Mapping[str, Any], request: Request
    # ) -> Mapping[str, Any]:
    #     """
    #     Exchange code for access_token.
    #     """
    #     try:
    #         """
    #         IMPLEMENT YOUR CREDENTIALS EXCHANGE HERE
    #         """
    #     except Exception as e:
    #         raise ToolProviderOAuthError(str(e))
    #     return dict()

    # def _oauth_refresh_credentials(
    #     self, redirect_uri: str, system_credentials: Mapping[str, Any], credentials: Mapping[str, Any]
    # ) -> OAuthCredentials:
    #     """
    #     Refresh the credentials
    #     """
    #     return OAuthCredentials(credentials=credentials, expires_at=-1)

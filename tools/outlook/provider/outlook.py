from typing import Any
import requests

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
import msal


class OutlookProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            # Check required fields
            required_fields = ["client_id", "client_secret", "tenant_id", "user_email"]
            for field in required_fields:
                if field not in credentials or not credentials.get(field):
                    raise ToolProviderCredentialValidationError(f"Azure AD {field} is required.")

            # Get access token
            access_token = self._get_access_token(
                credentials["client_id"],
                credentials["client_secret"],
                credentials["tenant_id"]
            )
            
            if not access_token:
                raise ToolProviderCredentialValidationError("Failed to acquire access token.")
            
            # Validate email access
            if not self._validate_email_access(access_token, credentials["user_email"]):
                raise ToolProviderCredentialValidationError(f"Failed to access email: {credentials['user_email']}")
            
        except ToolProviderCredentialValidationError:
            raise
        except Exception as e:
            raise ToolProviderCredentialValidationError(f"Credential validation failed: {str(e)}")

    def _get_access_token(self, client_id: str, client_secret: str, tenant_id: str) -> str:
        """
        Get access token using client credentials flow
        """
        try:
            app = msal.ConfidentialClientApplication(
                client_id=client_id,
                client_credential=client_secret,
                authority=f"https://login.microsoftonline.com/{tenant_id}"
            )
            
            result = app.acquire_token_for_client(
                scopes=["https://graph.microsoft.com/.default"]
            )
            
            if "access_token" in result:
                return result["access_token"]
            else:
                error_desc = result.get("error_description", "Unknown error")
                raise ToolProviderCredentialValidationError(f"Token acquisition failed: {error_desc}")
                
        except Exception as e:
            raise ToolProviderCredentialValidationError(f"Error getting access token: {str(e)}")

    def _validate_email_access(self, access_token: str, user_email: str) -> bool:
        """
        Validate if we can access the user's mailbox by listing messages in the inbox
        """
        try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            # Try to list messages in the inbox as a validation step
            response = requests.get(
                f"https://graph.microsoft.com/v1.0/users/{user_email}/mailFolders/inbox/messages?$top=1",
                headers=headers,
                timeout=30
            )
            if response.status_code == 200:
                return True
            elif response.status_code == 401:
                raise ToolProviderCredentialValidationError("Authentication failed. Token may be expired.")
            elif response.status_code == 403:
                raise ToolProviderCredentialValidationError("Access denied. Check app permissions and admin consent.")
            elif response.status_code == 404:
                raise ToolProviderCredentialValidationError(f"User '{user_email}' not found.")
            else:
                raise ToolProviderCredentialValidationError(f"Failed to access email: {response.text}")
        except requests.exceptions.RequestException as e:
            raise ToolProviderCredentialValidationError(f"Network error when validating email: {str(e)}")
        except Exception as e:
            raise ToolProviderCredentialValidationError(f"Error validating email access: {str(e)}")
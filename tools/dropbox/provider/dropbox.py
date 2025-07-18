from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
import dropbox
from dropbox.exceptions import AuthError

from dropbox_utils import DropboxUtils


class DropboxProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            # Check if access_token is provided in credentials
            if "access_token" not in credentials or not credentials.get("access_token"):
                raise ToolProviderCredentialValidationError("Dropbox access token is required.")
            
            # Try to authenticate with Dropbox using the access token
            try:
                # Use the utility function to get a client
                DropboxUtils.get_client(credentials.get("access_token"))
            except AuthError as e:
                raise ToolProviderCredentialValidationError(f"Invalid Dropbox access token: {str(e)}")
            except Exception as e:
                raise ToolProviderCredentialValidationError(f"Failed to connect to Dropbox: {str(e)}")
                
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))

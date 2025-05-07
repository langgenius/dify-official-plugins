from typing import Any

import smartsheet
from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class SmartsheetProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            # Check if API key is provided
            if "api_key" not in credentials or not credentials.get("api_key"):
                raise ToolProviderCredentialValidationError("Smartsheet API key is required.")
            
            # Attempt to initialize the Smartsheet client and make a simple API call to validate
            api_key = credentials.get("api_key")
            client = smartsheet.Smartsheet(api_key)
            
            # Get user info as a simple validation test
            user_info = client.Users.get_current_user()
            
            # If we get here, the credentials are valid
        except smartsheet.exceptions.SmartsheetException as e:
            raise ToolProviderCredentialValidationError(f"Invalid Smartsheet API key: {str(e)}")
        except Exception as e:
            raise ToolProviderCredentialValidationError(f"Error validating Smartsheet credentials: {str(e)}")

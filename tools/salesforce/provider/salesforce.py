from typing import Any

from provider.client import create_client

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

try:
    from simple_salesforce import SalesforceAuthenticationFailed
except ImportError:
    raise ImportError(
        "simple-salesforce is declared in pyproject.toml. Run `uv sync` in the plugin directory."
    )


class SalesforceProvider(ToolProvider):
    
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """
        Validate Salesforce credentials by attempting to authenticate
        """
        try:
            # Attempt to authenticate with Salesforce
            try:
                # Create Salesforce connection
                sf = create_client(credentials)
                
                # Test the connection by making a simple query
                sf.query("SELECT Id FROM User LIMIT 1")
                
            except SalesforceAuthenticationFailed as e:
                raise ToolProviderCredentialValidationError(
                    f"Invalid Salesforce credentials. Please check the credentials for your selected authentication method. Error: {str(e)}"
                )
            except Exception as e:
                raise ToolProviderCredentialValidationError(
                    f"Failed to connect to Salesforce: {str(e)}"
                )
                
        except ToolProviderCredentialValidationError:
            raise
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))

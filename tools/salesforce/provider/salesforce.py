from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

try:
    from simple_salesforce import Salesforce, SalesforceAuthenticationFailed
except ImportError:
    raise ImportError("Please install simple-salesforce: pip install simple-salesforce~=0.1.45")


class SalesforceProvider(ToolProvider):
    
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """
        Validate Salesforce credentials by attempting to authenticate
        """
        try:
            # Extract credentials
            username = credentials.get("username")
            password = credentials.get("password")
            security_token = credentials.get("security_token")
            domain = credentials.get("domain")  # Optional: 'test' for sandbox, None for production
            
            # Validate required fields
            if not username:
                raise ToolProviderCredentialValidationError("Salesforce username is required.")
            
            if not password:
                raise ToolProviderCredentialValidationError("Salesforce password is required.")
            
            if not security_token:
                raise ToolProviderCredentialValidationError("Salesforce security token is required.")
            
            # Attempt to authenticate with Salesforce
            try:
                # Create Salesforce connection
                sf = Salesforce(
                    username=username,
                    password=password,
                    security_token=security_token,
                    domain=domain if domain else None
                )
                
                # Test the connection by making a simple query
                sf.query("SELECT Id FROM User LIMIT 1")
                
            except SalesforceAuthenticationFailed as e:
                raise ToolProviderCredentialValidationError(
                    f"Invalid Salesforce credentials. Please check your username, password, and security token. Error: {str(e)}"
                )
            except Exception as e:
                raise ToolProviderCredentialValidationError(
                    f"Failed to connect to Salesforce: {str(e)}"
                )
                
        except ToolProviderCredentialValidationError:
            raise
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))

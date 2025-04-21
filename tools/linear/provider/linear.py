from typing import Any, Optional, Dict

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from client.Linear import Linear
from client.Exceptions import LinearApiException, LinearAuthenticationException


class LinearProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            api_key = credentials.get('linear_api_key')
            if not api_key:
                raise ToolProviderCredentialValidationError('API key is required')

            # Test API key by creating a Linear client and making a simple request
            linear_client = Linear(api_key)
            
            # Try to get the viewer information as a validation test
            viewer_data = linear_client.get_viewer()
            
            if not viewer_data or not viewer_data.get('id'):
                raise ToolProviderCredentialValidationError('Invalid API key or insufficient permissions')
                
        except LinearAuthenticationException:
            raise ToolProviderCredentialValidationError('Invalid API key')
        except LinearApiException as e:
            raise ToolProviderCredentialValidationError(f'Linear API error: {str(e)}')
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))
    
    def get_linear_client(self, credentials: Dict[str, Any]) -> Linear:
        """Return Linear client instance that can be used by tools"""
        api_key = credentials.get('linear_api_key', '')
        return Linear(api_key)

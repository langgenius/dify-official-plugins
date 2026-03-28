from typing import Any
from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from liteparse import LiteParse

class DifyLiteparseProvider(ToolProvider):
    
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """
        Validates the LlamaCloud API Key by attempting to initialize the parser.
        """
        api_key = credentials.get('api_key')
        if not api_key:
            raise ToolProviderCredentialValidationError("API Key is required")
        
        try:
            # We initialize the parser; if the key is structurally invalid, 
            # some SDKs throw an error here. 
            parser = LiteParse(api_key=api_key)
            # Optional: You could do a dummy small call here if LiteParse has a 'me' or 'status' endpoint
        except Exception as e:
            raise ToolProviderCredentialValidationError(f"Invalid LlamaCloud API Key: {str(e)}")
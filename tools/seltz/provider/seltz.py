from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from seltz import (
    Seltz,
    SeltzAuthenticationError,
    SeltzConfigurationError,
    SeltzConnectionError,
)
from seltz.types import Includes


class SeltzProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """
        Validate Seltz API credentials by performing a test search.
        """
        api_key = credentials.get("api_key")
        if not api_key:
            raise ToolProviderCredentialValidationError(
                "Seltz API key is required"
            )

        try:
            # Perform a test search to validate credentials
            client = Seltz(api_key=api_key)
            client.search("test", includes=Includes(max_documents=1))
        except SeltzAuthenticationError:
            raise ToolProviderCredentialValidationError(
                "Invalid Seltz API key."
            )
        except SeltzConfigurationError:
            raise ToolProviderCredentialValidationError(
                "Seltz configuration error. Please check your settings."
            )
        except SeltzConnectionError:
            raise ToolProviderCredentialValidationError(
                "Could not connect to Seltz API. Please try again later."
            )
        except Exception:
            raise ToolProviderCredentialValidationError(
                "Failed to validate Seltz credentials due to an unexpected error."
            )

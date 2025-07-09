from typing import Any
import requests

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class AttioProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            # Get credentials
            api_token = credentials.get("attio_api_token")

            # Validate required credentials
            if not api_token:
                raise ToolProviderCredentialValidationError(
                    "Attio API Token is required"
                )

            headers = {"Authorization": "Bearer " + api_token}

            url = "https://api.attio.com/v2/objects"

            # Try to fetch tables list to validate credentials
            response = requests.request("GET", url, headers=headers)

            if response.status_code == 401:
                raise ToolProviderCredentialValidationError("Invalid API token")
            elif response.status_code != 200:
                raise ToolProviderCredentialValidationError(
                    f"Failed to connect to Attio API. Status code: {response.status_code}, message: {response.text}"
                )

        except ToolProviderCredentialValidationError:
            raise
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"Failed to validate credentials: {str(e)}"
            )

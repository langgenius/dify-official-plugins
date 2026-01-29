from typing import Any

import plivo
from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class PlivoSmsProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            auth_id = credentials["auth_id"]
            auth_token = credentials["auth_token"]
            client = plivo.RestClient(auth_id=auth_id, auth_token=auth_token)
            client.account.get()
        except plivo.exceptions.AuthenticationError as e:
            raise ToolProviderCredentialValidationError(
                "Invalid Plivo Auth ID or Auth Token."
            ) from e
        except KeyError as e:
            raise ToolProviderCredentialValidationError(
                f"Missing required credential: {e}"
            ) from e
        except plivo.exceptions.PlivoRestError as e:
            raise ToolProviderCredentialValidationError(
                f"Plivo API error during validation: {e}"
            ) from e
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"An unexpected error occurred while validating Plivo credentials: {e}"
            ) from e

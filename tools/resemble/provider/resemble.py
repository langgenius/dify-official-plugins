from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from tools.resemble_api import ResembleClient, ResembleError


class ResembleProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """Validate the Resemble API key without consuming detection credits.
        Only a clear auth failure (401/403) is treated as invalid; transient
        network/other errors do not reject an otherwise-valid key."""
        try:
            client = ResembleClient(
                api_key=credentials.get("resemble_api_key"),
                base_url=credentials.get("base_url"),
            )
            client.validate_key()
        except ResembleError as exc:
            raise ToolProviderCredentialValidationError(str(exc))
        except Exception as exc:  # noqa: BLE001 — surface anything else as a validation error
            raise ToolProviderCredentialValidationError(str(exc))

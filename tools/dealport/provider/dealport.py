from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from utils import DealportApiError, request_dealport


class DealportProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        api_key = str(credentials.get("api_key") or "").strip()
        if not api_key:
            raise ToolProviderCredentialValidationError("Dealport API key is required.")
        try:
            request_dealport(credentials, "GET", "/balance", timeout=15)
        except DealportApiError as exc:
            raise ToolProviderCredentialValidationError(str(exc)) from exc
        except Exception as exc:
            raise ToolProviderCredentialValidationError(
                f"Failed to validate Dealport credentials ({type(exc).__name__})."
            ) from exc

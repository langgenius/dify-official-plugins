from typing import Dict, Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from tools.hap_api_utils import HapRequest


class HapProvider(ToolProvider):

    def _validate_credentials(self, credentials: Dict[str, Any]) -> None:
        appkey = credentials.get("appkey")
        sign = credentials.get("sign")

        if not appkey or not sign:
            raise ToolProviderCredentialValidationError("Appkey and Sign are required.")

        try:
            client = HapRequest(credentials)
            resp = client.get("/v3/app")
        except Exception as e:
            # Wrap any network/parse errors
            raise ToolProviderCredentialValidationError(f"Test connection failed: {e}")

        # Business success check
        if isinstance(resp, dict) and resp.get("success") is True:
            return
        elif isinstance(resp, dict):
            raise ToolProviderCredentialValidationError(f"Test connection failed: {resp}")
        else:
            raise ToolProviderCredentialValidationError(f"Test connection failed")
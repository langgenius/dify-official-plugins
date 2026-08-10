from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from tools.base import DASHSCOPE_CN_BASE_URL, DASHSCOPE_INTL_BASE_URL
from tools.search_memory import SearchMemoryTool


class BailianMemoryProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        api_key = credentials.get("dashscope_api_key")
        if not api_key:
            raise ToolProviderCredentialValidationError("DashScope API Key is required")
        try:
            for _ in SearchMemoryTool.from_credentials(credentials).invoke(
                tool_parameters={
                    "user_id": "__dify_credential_validation__",
                    "query": "test",
                    "top_k": 1,
                }
            ):
                pass
        except ToolProviderCredentialValidationError:
            raise
        except Exception as e:
            error_msg = str(e)
            if "InvalidApiKey" in error_msg or "401" in error_msg:
                # Both regions reject foreign keys with identical bodies, so
                # name the host that was actually hit.
                intl = credentials.get("use_international_endpoint", "false") == "true"
                endpoint = (DASHSCOPE_INTL_BASE_URL if intl else DASHSCOPE_CN_BASE_URL).removeprefix("https://")
                raise ToolProviderCredentialValidationError(
                    f"DashScope rejected the API key at {endpoint} (InvalidApiKey). "
                    f"Model Studio keys are region-specific: if this key is from the "
                    f"{'China (Beijing)' if intl else 'International (Singapore)'} console, "
                    f"flip the 'Use International Endpoint' setting to match it."
                )
            # Other errors (like empty results) are fine - the key is valid

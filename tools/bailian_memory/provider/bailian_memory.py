from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

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
                raise ToolProviderCredentialValidationError("Invalid DashScope API Key")
            # Other errors (like empty results) are fine - the key is valid

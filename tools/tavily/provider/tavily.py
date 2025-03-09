from typing import Any
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from tools.tavily_search import TavilySearchTool
from dify_plugin import ToolProvider


class TavilyProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            TavilySearchTool.from_credentials(credentials, user_id="").invoke(
                tool_parameters={
                    "query": "Dify AI",
                }
            )
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))

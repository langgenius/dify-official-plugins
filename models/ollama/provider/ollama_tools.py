from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from tools.web_search import OllamaWebSearchTool


class OllamaToolsProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            for _ in OllamaWebSearchTool.from_credentials(credentials, user_id="").invoke(
                tool_parameters={"query": "what is ollama", "max_results": 1}
            ):
                pass
        except Exception as ex:
            raise ToolProviderCredentialValidationError(str(ex))

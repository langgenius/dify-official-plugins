from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from tools.client import call_ollama_cloud_api


class OllamaToolsProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            call_ollama_cloud_api(
                credentials=credentials,
                path="web_search",
                payload={"query": "ping", "max_results": 1},
            )
        except Exception as ex:
            raise ToolProviderCredentialValidationError(str(ex))

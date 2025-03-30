from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from tools.bing_web_search import BingWebSearchTool


class BingProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            for _ in BingWebSearchTool.from_credentials(credentials).invoke(
                tool_parameters={
                    "query": "test",
                    "enable_computation": credentials.get("allow_computation", False),
                    "enable_entities": credentials.get("allow_entities", False),
                    "enable_news": credentials.get("allow_news", False),
                    "enable_related_search": credentials.get("allow_related_searches", False),
                    "enable_webpages": credentials.get("allow_web_pages", False),
                    "limit": 10,
                    "result_type": "link",
                    "market": "US",
                    "language": "en",
                },
            ):
                pass
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))

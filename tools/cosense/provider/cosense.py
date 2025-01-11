from typing import Any, Generator

from tools.cosense_search import CosenseSearchTool

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class CosenseProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            for _ in CosenseSearchTool.from_credentials(credentials).invoke(
                tool_parameters={"project_name": "help-jp", "query": "test"},
            ):
                pass
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e)) from e

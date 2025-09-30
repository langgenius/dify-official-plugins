from typing import Any
from dify_plugin import ToolProvider


class OracleDbPluginProvider(ToolProvider):
    
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        # This plugin does not require OAuth functionality, no credential validation is performed
        # Empty implementation to meet Dify plugin system interface requirements
        pass

from dify_plugin import ToolProvider
from typing import Any

class SomarkProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """
        Validate credentials.
        """
        if not credentials.get("api_key"):
             raise ValueError("API Key is required")

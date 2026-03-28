from typing import Any
from dify_plugin import ToolProvider

class LiteParseProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """
        LiteParse is local-first and does not require credentials validation.
        """
        pass
